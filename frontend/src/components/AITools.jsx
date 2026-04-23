import { useEffect, useMemo, useRef, useState } from "react";

import {
  askLlmStream,
  exportNaturalSearch,
  fetchLlmModels,
  fetchLlmStatus,
  fetchNaturalSearch,
  fetchTagSuggestions
} from "../lib/api";

const PAGE_SIZE = 10;
const LONG_WAIT_MS = 15000;

function SearchResultCard({ item, onOpenRecipe }) {
  return (
    <article className="recipe-card ai-result-card">
      <div className="recipe-card-header">
        <h3>{item.name}</h3>
        <span>{item.score}</span>
      </div>
      <p className="recipe-meta">
        {[item.library_section, item.section_name, item.cuisine || item.sub_cuisine].filter(Boolean).join(" / ") || "未归类"}
      </p>
      <div className="tag-row compact-tag-row">
        <span className="tag">{item.record_kind === "backlog" ? item.backlog_status : "正式菜谱"}</span>
        {item.bmd_flag ? <span className="tag">BMD</span> : null}
        {item.cc_flag ? <span className="tag">CC</span> : null}
      </div>
      <div className="detail-section">
        <h3>命中原因</h3>
        <ul className="reason-list">
          {item.reasons.map((reason) => (
            <li key={`${item.id}-${reason}`}>{reason}</li>
          ))}
        </ul>
      </div>
      <div className="action-row">
        <button type="button" className="action-button secondary" onClick={() => onOpenRecipe(item.id)}>
          打开条目
        </button>
      </div>
    </article>
  );
}

function RecipeRefCard({ item, onOpenRecipe }) {
  return (
    <article className="history-card">
      <div className="panel-header">
        <div>
          <h3>{item.name}</h3>
          <p className="recipe-meta">
            {[item.library_section, item.section_name].filter(Boolean).join(" / ") || "未归类"}
          </p>
        </div>
        <div className="tag-row compact-tag-row">
          {item.source ? <span className="tag">{item.source === "selected" ? "当前条目" : "检索候选"}</span> : null}
          {item.score ? <span className="tag muted">分数 {item.score}</span> : null}
        </div>
      </div>
      <div className="action-row">
        <button type="button" className="action-button secondary" onClick={() => onOpenRecipe(item.id)}>
          打开条目
        </button>
      </div>
    </article>
  );
}

function ChatBubble({ item }) {
  return (
    <article className="history-card">
      <div className="panel-header">
        <h3>{item.role === "user" ? "你" : "模型"}</h3>
      </div>
      <p style={{ whiteSpace: "pre-wrap" }}>{item.content}</p>
    </article>
  );
}

function InterpretationPanel({ interpretation, retrieval }) {
  if (!interpretation) {
    return null;
  }

  const sourceLabel =
    interpretation.source === "llm"
      ? "模型解释"
      : interpretation.source === "fast_path"
        ? "快速回复"
        : "回退规则";

  return (
    <section className="detail-section">
      <h3>概念解释</h3>
      <div className="detail-grid detail-grid-wide">
        <div className="detail-stat">
          <span>来源</span>
          <strong>{sourceLabel}</strong>
        </div>
        <div className="detail-stat">
          <span>检索短句</span>
          <strong>{retrieval?.query || interpretation.retrieval_query || "-"}</strong>
        </div>
      </div>
      <div className="tag-row">
        {(interpretation.concepts || []).map((item) => (
          <span key={`concept-${item}`} className="tag">
            概念: {item}
          </span>
        ))}
        {(interpretation.expanded_terms || []).map((item) => (
          <span key={`expanded-${item}`} className="tag">
            展开词: {item}
          </span>
        ))}
        {(interpretation.constraints || []).map((item) => (
          <span key={`constraint-${item}`} className="tag muted">
            限制: {item}
          </span>
        ))}
      </div>
      {interpretation.intent ? <p className="recipe-meta">意图：{interpretation.intent}</p> : null}
      {interpretation.notes ? <p className="recipe-meta">备注：{interpretation.notes}</p> : null}
    </section>
  );
}

function pipelineStageLabel(stage) {
  if (stage === "fast_path") {
    return "快速回复中";
  }
  if (stage === "interpretation") {
    return "正在解释问题";
  }
  if (stage === "retrieval") {
    return "正在检索菜谱";
  }
  if (stage === "answer") {
    return "正在生成回答";
  }
  return "";
}

export default function AITools({ selectedRecipe, selectedRecipeId, onOpenRecipe }) {
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchOffset, setSearchOffset] = useState(0);

  const [tagSuggestions, setTagSuggestions] = useState(null);
  const [tagLoading, setTagLoading] = useState(false);
  const [tagError, setTagError] = useState("");

  const [llmStatus, setLlmStatus] = useState(null);
  const [llmModels, setLlmModels] = useState([]);
  const [llmModel, setLlmModel] = useState("");
  const [llmQuestion, setLlmQuestion] = useState("");
  const [llmTopK, setLlmTopK] = useState(6);
  const [useSelectedRecipeContext, setUseSelectedRecipeContext] = useState(true);
  const [showReasoning, setShowReasoning] = useState(false);
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmError, setLlmError] = useState("");
  const [llmHistory, setLlmHistory] = useState([]);
  const [llmResult, setLlmResult] = useState(null);
  const [llmStage, setLlmStage] = useState("");
  const [longWaitHint, setLongWaitHint] = useState("");
  const [streamThinking, setStreamThinking] = useState("");
  const [streamAnswer, setStreamAnswer] = useState("");
  const [streamInterpretation, setStreamInterpretation] = useState(null);
  const [streamRetrieval, setStreamRetrieval] = useState(null);

  const longWaitTimerRef = useRef(null);

  useEffect(() => {
    let active = true;

    async function loadTagSuggestions() {
      if (!selectedRecipeId) {
        setTagSuggestions(null);
        return;
      }

      setTagLoading(true);
      setTagError("");

      try {
        const result = await fetchTagSuggestions(selectedRecipeId);
        if (active) {
          setTagSuggestions(result);
        }
      } catch (requestError) {
        if (active) {
          setTagError(requestError.message);
        }
      } finally {
        if (active) {
          setTagLoading(false);
        }
      }
    }

    loadTagSuggestions();

    return () => {
      active = false;
    };
  }, [selectedRecipeId]);

  useEffect(() => {
    let active = true;

    async function loadLlmStatus() {
      try {
        const [statusResult, modelResult] = await Promise.all([fetchLlmStatus(), fetchLlmModels()]);
        if (!active) {
          return;
        }
        const models = modelResult.items || [];
        setLlmStatus(statusResult);
        setLlmModels(models);
        setLlmModel((current) => current || statusResult.default_model || models[0]?.name || "");
      } catch (requestError) {
        if (!active) {
          return;
        }
        setLlmStatus({
          available: false,
          error: requestError.message
        });
      }
    }

    loadLlmStatus();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (longWaitTimerRef.current) {
        window.clearTimeout(longWaitTimerRef.current);
      }
    };
  }, []);

  function resetLlmProgress() {
    if (longWaitTimerRef.current) {
      window.clearTimeout(longWaitTimerRef.current);
      longWaitTimerRef.current = null;
    }
    setLlmStage("");
    setLongWaitHint("");
    setStreamThinking("");
    setStreamAnswer("");
    setStreamInterpretation(null);
    setStreamRetrieval(null);
  }

  async function runSearch(offset = 0) {
    if (!query.trim()) {
      setSearchResult(null);
      return;
    }

    setSearchLoading(true);
    setSearchError("");

    try {
      const result = await fetchNaturalSearch(query.trim(), { limit: PAGE_SIZE, offset });
      setSearchResult(result);
      setSearchOffset(offset);
    } catch (requestError) {
      setSearchError(requestError.message);
    } finally {
      setSearchLoading(false);
    }
  }

  async function runLlmQuestion() {
    if (!llmQuestion.trim()) {
      return;
    }

    const userMessage = llmQuestion.trim();
    const requestHistory = llmHistory.map((item) => ({
      role: item.role,
      content: item.content
    }));
    const withContext = useSelectedRecipeContext ? selectedRecipeId || null : null;

    setLlmLoading(true);
    setLlmError("");
    resetLlmProgress();
    setLlmStage(!withContext && llmHistory.length === 0 && userMessage.length <= 8 ? "fast_path" : "interpretation");
    longWaitTimerRef.current = window.setTimeout(() => {
      setLongWaitHint("本地模型响应较慢。可以继续等待，也可以稍后重试。");
    }, LONG_WAIT_MS);

    try {
      const result = await askLlmStream(
        {
          message: userMessage,
          model: llmModel || undefined,
          selected_recipe_id: withContext,
          top_k: llmTopK,
          history: requestHistory,
          show_reasoning: showReasoning
        },
        {
          onEvent: (event) => {
            if (event.type === "stage") {
              setLlmStage(event.stage || "");
            } else if (event.type === "interpretation") {
              setStreamInterpretation(event.data || null);
            } else if (event.type === "retrieval") {
              setStreamRetrieval(event.data || null);
            } else if (event.type === "thinking_chunk") {
              setStreamThinking((current) => current + (event.delta || ""));
            } else if (event.type === "answer_chunk") {
              setStreamAnswer((current) => current + (event.delta || ""));
            }
          }
        }
      );

      setLlmHistory((current) => [
        ...current,
        { role: "user", content: userMessage },
        { role: "assistant", content: result.answer }
      ]);
      setLlmResult(result);
      setLlmQuestion("");
      setStreamInterpretation(result.interpretation || null);
      setStreamRetrieval(result.retrieval || null);
      setStreamAnswer(result.answer || "");
      if (result.interpretation?.raw_thinking) {
        setStreamThinking(result.interpretation.raw_thinking);
      }
      setLlmStage(result.pipeline?.mode === "fast_path" ? "fast_path" : "answer");
      setLongWaitHint("");
    } catch (requestError) {
      setLlmError(requestError.message);
      setLlmStage("");
    } finally {
      if (longWaitTimerRef.current) {
        window.clearTimeout(longWaitTimerRef.current);
        longWaitTimerRef.current = null;
      }
      setLlmLoading(false);
    }
  }

  function clearChat() {
    setLlmHistory([]);
    setLlmResult(null);
    setLlmError("");
    resetLlmProgress();
  }

  const total = searchResult?.total ?? 0;
  const currentStart = total === 0 ? 0 : searchOffset + 1;
  const currentEnd = Math.min(searchOffset + PAGE_SIZE, total);
  const canGoPrev = searchOffset > 0;
  const canGoNext = searchOffset + PAGE_SIZE < total;

  const llmModelOptions = useMemo(() => {
    const seen = new Set();
    return [llmStatus?.default_model, ...llmModels.map((item) => item.name)].filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
  }, [llmModels, llmStatus]);

  const displayedInterpretation = llmResult?.interpretation || streamInterpretation;
  const displayedRetrieval = llmResult?.retrieval || streamRetrieval;

  return (
    <div className="section-stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">LLM Assistant</p>
            <h2>智能问答</h2>
          </div>
        </div>

        <div className="detail-section">
          <div className="detail-grid detail-grid-wide">
            <div className="detail-stat">
              <span>Ollama</span>
              <strong>{llmStatus?.available ? "已连接" : "未连接"}</strong>
            </div>
            <div className="detail-stat">
              <span>地址</span>
              <strong>{llmStatus?.base_url || "-"}</strong>
            </div>
            <div className="detail-stat">
              <span>默认模型</span>
              <strong>{llmStatus?.default_model || "-"}</strong>
            </div>
            <div className="detail-stat">
              <span>已发现模型</span>
              <strong>{llmModels.length}</strong>
            </div>
          </div>
          {llmStatus?.error ? <div className="error-banner">{llmStatus.error}</div> : null}
        </div>

        <div className="filter-bar">
          <label className="filter-shell">
            <span>模型</span>
            <select value={llmModel} onChange={(event) => setLlmModel(event.target.value)}>
              {llmModelOptions.length === 0 ? <option value="">未发现模型</option> : null}
              {llmModelOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="filter-shell">
            <span>检索候选数</span>
            <select value={String(llmTopK)} onChange={(event) => setLlmTopK(Number(event.target.value))}>
              {[4, 6, 8, 10].map((item) => (
                <option key={item} value={String(item)}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="search-shell" htmlFor="llm-question">
          <span>问题</span>
          <textarea
            id="llm-question"
            rows={4}
            placeholder="例如：请帮我找出 10 道适合病号吃的菜"
            value={llmQuestion}
            onChange={(event) => setLlmQuestion(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                runLlmQuestion();
              }
            }}
          />
        </label>

        {selectedRecipe ? (
          <div className="detail-section">
            <h3>当前已选菜谱</h3>
            <p className="recipe-meta">
              {selectedRecipe.name}
              {selectedRecipe.library_section ? ` / ${selectedRecipe.library_section}` : ""}
              {selectedRecipe.section_name ? ` / ${selectedRecipe.section_name}` : ""}
            </p>
            <label className="toggle-shell" style={{ marginTop: 12 }}>
              <input
                type="checkbox"
                checked={useSelectedRecipeContext}
                onChange={(event) => setUseSelectedRecipeContext(event.target.checked)}
              />
              <span>把当前菜谱作为上下文</span>
            </label>
          </div>
        ) : null}

        <label className="toggle-shell">
          <input
            type="checkbox"
            checked={showReasoning}
            onChange={(event) => setShowReasoning(event.target.checked)}
          />
          <span>显示推理过程</span>
        </label>

        <div className="action-row">
          <button
            type="button"
            className="action-button"
            onClick={runLlmQuestion}
            disabled={llmLoading || !llmQuestion.trim() || !llmStatus?.available}
          >
            {llmLoading ? "处理中..." : "发送"}
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={clearChat}
            disabled={llmLoading || llmHistory.length === 0}
          >
            清空对话
          </button>
        </div>

        {llmLoading && llmStage ? (
          <div className="warning-banner">
            {pipelineStageLabel(llmStage)}
            {longWaitHint ? `。${longWaitHint}` : ""}
          </div>
        ) : null}

        {!llmLoading && longWaitHint ? <div className="warning-banner">{longWaitHint}</div> : null}
        {llmError ? <div className="error-banner">{llmError}</div> : null}

        {showReasoning && (streamThinking || displayedInterpretation) ? (
          <section className="detail-section">
            <h3>推理过程</h3>
            {displayedInterpretation ? (
              <p className="recipe-meta">
                {displayedInterpretation.intent ? `意图：${displayedInterpretation.intent}` : "正在生成解释..."}
              </p>
            ) : null}
            <pre className="stream-box">{streamThinking || "正在等待模型推理输出..."}</pre>
          </section>
        ) : null}

        {llmLoading && streamAnswer ? (
          <section className="detail-section">
            <h3>实时回答</h3>
            <pre className="stream-box">{streamAnswer}</pre>
          </section>
        ) : null}

        {llmHistory.length > 0 ? (
          <section className="detail-section">
            <h3>对话历史</h3>
            <div className="section-stack">
              {llmHistory.map((item, index) => (
                <ChatBubble key={`${item.role}-${index}`} item={item} />
              ))}
            </div>
          </section>
        ) : null}

        {llmResult || displayedInterpretation ? (
          <div className="section-stack">
            <InterpretationPanel interpretation={displayedInterpretation} retrieval={displayedRetrieval} />

            {displayedRetrieval ? (
              <section className="detail-section">
                <h3>检索阶段</h3>
                <div className="detail-grid detail-grid-wide">
                  <div className="detail-stat">
                    <span>命中条目</span>
                    <strong>{displayedRetrieval.total ?? 0}</strong>
                  </div>
                  <div className="detail-stat">
                    <span>规则理解</span>
                    <strong>{Object.values(displayedRetrieval.understanding || {}).flat().length}</strong>
                  </div>
                  <div className="detail-stat">
                    <span>执行模式</span>
                    <strong>{llmResult?.pipeline?.mode === "fast_path" ? "快速回复" : "检索增强"}</strong>
                  </div>
                </div>
                <div className="tag-row">
                  {(displayedRetrieval.understanding?.library_sections || []).map((item) => (
                    <span key={`llm-section-${item}`} className="tag">
                      专题库: {item}
                    </span>
                  ))}
                  {(displayedRetrieval.understanding?.section_names || []).map((item) => (
                    <span key={`llm-group-${item}`} className="tag">
                      分组: {item}
                    </span>
                  ))}
                  {(displayedRetrieval.understanding?.cuisines || []).map((item) => (
                    <span key={`llm-cuisine-${item}`} className="tag">
                      菜系: {item}
                    </span>
                  ))}
                  {(displayedRetrieval.understanding?.include_ingredients || []).map((item) => (
                    <span key={`llm-include-${item}`} className="tag">
                      食材: {item}
                    </span>
                  ))}
                  {(displayedRetrieval.understanding?.exclude_ingredients || []).map((item) => (
                    <span key={`llm-exclude-${item}`} className="tag muted">
                      排除: {item}
                    </span>
                  ))}
                  {(displayedRetrieval.understanding?.free_text_terms || []).map((item) => (
                    <span key={`llm-term-${item}`} className="tag">
                      关键词: {item}
                    </span>
                  ))}
                </div>
                {displayedRetrieval.items?.length ? (
                  <div className="recipe-list ai-result-list">
                    {displayedRetrieval.items.map((item) => (
                      <RecipeRefCard key={`retrieval-${item.id}-${item.source}`} item={item} onOpenRecipe={onOpenRecipe} />
                    ))}
                  </div>
                ) : (
                  <p>本轮没有检索到可用菜谱上下文。</p>
                )}
              </section>
            ) : null}

            {llmResult ? (
              <>
                <section className="detail-section">
                  <h3>回答阶段</h3>
                  <div className="detail-grid detail-grid-wide">
                    <div className="detail-stat">
                      <span>概念解释耗时</span>
                      <strong>{llmResult.pipeline?.interpretation_ms ?? 0} ms</strong>
                    </div>
                    <div className="detail-stat">
                      <span>检索耗时</span>
                      <strong>{llmResult.pipeline?.retrieval_ms ?? 0} ms</strong>
                    </div>
                    <div className="detail-stat">
                      <span>回答耗时</span>
                      <strong>{llmResult.pipeline?.answer_ms ?? 0} ms</strong>
                    </div>
                  </div>
                  <p style={{ whiteSpace: "pre-wrap" }}>{llmResult.answer}</p>
                </section>

                <section className="detail-section">
                  <h3>本轮引用</h3>
                  {llmResult.citations?.length ? (
                    <div className="recipe-list ai-result-list">
                      {llmResult.citations.map((item) => (
                        <RecipeRefCard key={`citation-${item.id}-${item.source || "citation"}`} item={item} onOpenRecipe={onOpenRecipe} />
                      ))}
                    </div>
                  ) : (
                    <p>本轮没有引用到可展示的条目。</p>
                  )}
                </section>
              </>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Natural Search</p>
            <h2>自然语言搜索</h2>
          </div>
        </div>

        <label className="search-shell" htmlFor="natural-query">
          <span>查询语句</span>
          <input
            id="natural-query"
            type="search"
            placeholder="例如：早餐里的面包类，不含番茄，偏广东菜"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                runSearch(0);
              }
            }}
          />
        </label>

        <div className="action-row">
          <button type="button" className="action-button" onClick={() => runSearch(0)} disabled={searchLoading}>
            {searchLoading ? "搜索中..." : "执行搜索"}
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={() => exportNaturalSearch(query.trim())}
            disabled={!query.trim() || searchLoading}
          >
            导出结果到 Excel
          </button>
        </div>

        {searchError ? <div className="error-banner">{searchError}</div> : null}

        {searchResult ? (
          <div className="section-stack">
            <section className="detail-section">
              <h3>系统理解</h3>
              <div className="tag-row">
                {(searchResult.understanding.library_sections || []).map((item) => (
                  <span key={`section-${item}`} className="tag">
                    专题库: {item}
                  </span>
                ))}
                {(searchResult.understanding.section_names || []).map((item) => (
                  <span key={`group-${item}`} className="tag">
                    分组: {item}
                  </span>
                ))}
                {(searchResult.understanding.cuisines || []).map((item) => (
                  <span key={`cuisine-${item}`} className="tag">
                    菜系: {item}
                  </span>
                ))}
                {(searchResult.understanding.statuses || []).map((item) => (
                  <span key={`status-${item}`} className="tag">
                    类型: {item}
                  </span>
                ))}
                {(searchResult.understanding.include_ingredients || []).map((item) => (
                  <span key={`include-${item}`} className="tag">
                    食材: {item}
                  </span>
                ))}
                {(searchResult.understanding.exclude_ingredients || []).map((item) => (
                  <span key={`exclude-${item}`} className="tag muted">
                    排除: {item}
                  </span>
                ))}
                {(searchResult.understanding.free_text_terms || []).map((item) => (
                  <span key={`term-${item}`} className="tag">
                    关键词: {item}
                  </span>
                ))}
              </div>
            </section>

            <section className="detail-section">
              <div className="panel-header ai-toolbar">
                <div>
                  <h3>搜索结果</h3>
                  <p className="recipe-meta">
                    当前显示 {currentStart}-{currentEnd} / 共 {total} 条
                  </p>
                </div>
                <div className="action-row">
                  <button
                    type="button"
                    className="action-button secondary"
                    disabled={!canGoPrev || searchLoading}
                    onClick={() => runSearch(Math.max(searchOffset - PAGE_SIZE, 0))}
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    className="action-button secondary"
                    disabled={!canGoNext || searchLoading}
                    onClick={() => runSearch(searchOffset + PAGE_SIZE)}
                  >
                    下一页
                  </button>
                </div>
              </div>

              {searchResult.items.length === 0 ? (
                <p>没有找到匹配条目。可以减少限制条件或换一种说法。</p>
              ) : (
                <div className="recipe-list ai-result-list">
                  {searchResult.items.map((item) => (
                    <SearchResultCard key={item.id} item={item} onOpenRecipe={onOpenRecipe} />
                  ))}
                </div>
              )}
            </section>
          </div>
        ) : (
          <div className="empty-state compact-empty-state">
            <h3>尚未执行搜索</h3>
            <p>输入口语化查询后，系统会给出分页结果，并支持导出到 Excel。</p>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Tag Suggestion</p>
            <h2>自动标签建议</h2>
          </div>
        </div>

        {!selectedRecipeId ? (
          <div className="empty-state compact-empty-state">
            <h3>未选择条目</h3>
            <p>先在菜谱库或搜索结果里打开一条记录，再查看标签建议。</p>
          </div>
        ) : null}

        {tagError ? <div className="error-banner">{tagError}</div> : null}

        {selectedRecipeId && tagLoading ? (
          <div className="empty-state compact-empty-state">
            <h3>加载标签建议中</h3>
          </div>
        ) : null}

        {selectedRecipeId && !tagLoading && tagSuggestions ? (
          <div className="section-stack">
            <section className="detail-section">
              <h3>当前条目</h3>
              <p>{tagSuggestions.recipe_name || selectedRecipe?.name}</p>
              <div className="tag-row">
                {(tagSuggestions.existing_tags || []).length === 0 ? (
                  <span className="tag muted">当前没有标签</span>
                ) : (
                  tagSuggestions.existing_tags.map((tag) => (
                    <span key={`existing-${tag}`} className="tag">
                      {tag}
                    </span>
                  ))
                )}
              </div>
            </section>

            <section className="detail-section">
              <h3>建议结果</h3>
              {tagSuggestions.items.length === 0 ? (
                <p>当前没有生成新的标签建议。</p>
              ) : (
                <div className="suggestion-list">
                  {tagSuggestions.items.map((item) => (
                    <article key={item.tag} className="detail-stat suggestion-card">
                      <span>{item.tag}</span>
                      <strong>{Math.round(item.confidence * 100)}%</strong>
                      <p>{item.reason}</p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        ) : null}
      </section>
    </div>
  );
}
