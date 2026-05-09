import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  askLlmStream,
  exportNaturalSearch,
  fetchDeepseekApiKeyStatus,
  fetchLlmModels,
  fetchLlmStatus,
  fetchNaturalSearch
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
  const isUser = item.role === "user";
  return (
    <article className={`chat-message ${isUser ? "user" : "assistant"}`}>
      <div className="chat-avatar">{isUser ? "你" : "AI"}</div>
      <div className="chat-bubble">
        <div className="chat-bubble-header">{isUser ? "你" : "模型"}</div>
        <div className="chat-answer">{item.content}</div>
      </div>
    </article>
  );
}

function StreamingAssistantBubble({ stage, answer, showReasoning, longWaitHint }) {
  const stageLabel = pipelineStageLabel(stage) || "正在处理";
  const stageDescription = pipelineStageDescription(stage);

  return (
    <article className="chat-message assistant streaming">
      <div className="chat-avatar">AI</div>
      <div className="chat-bubble">
        <div className="chat-bubble-header">
          <span>模型</span>
          <span className="chat-stage">{stageLabel}</span>
        </div>
        {showReasoning ? (
          <div className="chat-thinking">
            <strong>处理过程</strong>
            <p>{stageDescription}</p>
          </div>
        ) : null}
        <div className="chat-answer">
          {answer || "正在等待模型回答..."}
          <span className="chat-cursor" aria-hidden="true" />
        </div>
        {longWaitHint ? <div className="chat-hint">{longWaitHint}</div> : null}
      </div>
    </article>
  );
}

function InterpretationPanel({ interpretation, retrieval }) {
  if (!interpretation) {
    return null;
  }

  const sourceLabel = interpretationSourceLabel(interpretation.source);

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
  if (stage === "routing") {
    return "正在判断问题类型";
  }
  if (stage === "fast_path") {
    return "快速回复中";
  }
  if (stage === "interpretation") {
    return "正在解释问题";
  }
  if (stage === "external_interpretation") {
    return "DeepSeek 正在前置解析";
  }
  if (stage === "external_rerank") {
    return "DeepSeek 正在后处理";
  }
  if (stage === "retrieval") {
    return "正在检索菜谱";
  }
  if (stage === "answer") {
    return "正在生成回答";
  }
  if (stage === "general_answer") {
    return "正在直接回答";
  }
  return "";
}

function pipelineStageDescription(stage) {
  if (stage === "routing") {
    return "正在判断这次输入是否需要查询本地菜谱库。";
  }
  if (stage === "fast_path") {
    return "当前问题可以直接回复，不需要进入菜谱检索。";
  }
  if (stage === "interpretation") {
    return "正在把问题整理成可检索的关键词和限制条件。";
  }
  if (stage === "external_interpretation") {
    return "正在使用 DeepSeek 解析用户需求；不会发送完整菜谱内容。";
  }
  if (stage === "external_rerank") {
    return "正在对本地候选结果做辅助排序。";
  }
  if (stage === "retrieval") {
    return "正在从本地菜谱库检索候选，并整理引用条目。";
  }
  if (stage === "answer") {
    return "正在基于检索到的菜谱上下文生成回答。";
  }
  if (stage === "general_answer") {
    return "正在直接回答当前问题。";
  }
  return "正在处理当前请求。";
}

function interpretationSourceLabel(source) {
  if (source === "llm") {
    return "模型解释";
  }
  if (source === "deepseek") {
    return "DeepSeek前置解析";
  }
  if (source === "deepseek_fallback") {
    return "DeepSeek失败后回退";
  }
  if (source === "fast_path") {
    return "快速回复";
  }
  if (source === "route_general") {
    return "普通问答";
  }
  return "回退规则";
}

function buildDeepseekNoticeText(option, checked) {
  if (checked && option === "interpretation") {
    return "开启后，会把你当前输入的问题文本发送给 DeepSeek，用于解析需求、提取包含/排除/偏好条件；不会发送菜名、做法、食材列表或数据库内容。该操作可能产生 DeepSeek API 调用费用。";
  }
  if (checked && option === "rerank") {
    return "开启后，会先在本地检索更多候选，再把候选菜谱的脱敏摘要发送给 DeepSeek 做排序和解释。摘要可能包含菜名、分类、自动标签、简短食材/调料摘要和本地命中原因，不发送完整做法、备注或完整数据库。该操作可能产生 DeepSeek API 调用费用。";
  }
  if (option === "interpretation") {
    return "关闭后，需求解析将由本地大语言模型处理。隐私更强，但复杂需求的理解精度可能下降，速度也可能更慢。";
  }
  return "关闭后，候选排序和解释将只使用本地检索结果，不再发送候选摘要给 DeepSeek。隐私更强，但复杂需求的排序精度可能下降。";
}

function UnderstandingTags({ understanding }) {
  if (!understanding) {
    return null;
  }

  return (
    <div className="tag-row">
      {(understanding.library_sections || []).map((item) => (
        <span key={`section-${item}`} className="tag">
          专题库: {item}
        </span>
      ))}
      {(understanding.section_names || []).map((item) => (
        <span key={`group-${item}`} className="tag">
          分组: {item}
        </span>
      ))}
      {(understanding.cuisines || []).map((item) => (
        <span key={`cuisine-${item}`} className="tag">
          菜系: {item}
        </span>
      ))}
      {(understanding.statuses || []).map((item) => (
        <span key={`status-${item}`} className="tag">
          类型: {item}
        </span>
      ))}
      {(understanding.include_ingredients || []).map((item) => (
        <span key={`include-${item}`} className="tag">
          食材: {item}
        </span>
      ))}
      {(understanding.exclude_ingredients || []).map((item) => (
        <span key={`exclude-${item}`} className="tag muted">
          排除: {item}
        </span>
      ))}
      {(understanding.free_text_terms || []).map((item) => (
        <span key={`term-${item}`} className="tag">
          关键词: {item}
        </span>
      ))}
    </div>
  );
}

export default function AITools({ onOpenRecipe }) {
  const [activeTab, setActiveTab] = useState("chat");
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchOffset, setSearchOffset] = useState(0);

  const [llmStatus, setLlmStatus] = useState(null);
  const [llmModels, setLlmModels] = useState([]);
  const [llmModel, setLlmModel] = useState("");
  const [llmQuestion, setLlmQuestion] = useState("");
  const [llmTopK, setLlmTopK] = useState(6);
  const [showReasoning, setShowReasoning] = useState(true);
  const [useDeepseekInterpretation, setUseDeepseekInterpretation] = useState(false);
  const [allowExternalRerank, setAllowExternalRerank] = useState(false);
  const [deepseekApiKeyConfigured, setDeepseekApiKeyConfigured] = useState(false);
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmError, setLlmError] = useState("");
  const [llmHistory, setLlmHistory] = useState([]);
  const [llmResult, setLlmResult] = useState(null);
  const [llmStage, setLlmStage] = useState("");
  const [llmStatusRefreshing, setLlmStatusRefreshing] = useState(false);
  const [longWaitHint, setLongWaitHint] = useState("");
  const [streamAnswer, setStreamAnswer] = useState("");
  const [streamInterpretation, setStreamInterpretation] = useState(null);
  const [streamRetrieval, setStreamRetrieval] = useState(null);
  const [showDebugModal, setShowDebugModal] = useState(false);
  const [deepseekNotice, setDeepseekNotice] = useState(null);

  const longWaitTimerRef = useRef(null);
  const chatScrollRef = useRef(null);
  const llmAbortControllerRef = useRef(null);
  const streamAnswerRef = useRef("");

  const refreshLlmStatus = useCallback(async (isActive = () => true) => {
    if (isActive()) {
      setLlmStatusRefreshing(true);
    }

    try {
      const [statusResult, modelResult, deepseekStatus] = await Promise.all([
        fetchLlmStatus(),
        fetchLlmModels(),
        fetchDeepseekApiKeyStatus()
      ]);
      if (!isActive()) {
        return;
      }
      const models = modelResult.items || [];
      const modelNames = models.map((item) => item.name).filter(Boolean);
      setLlmStatus(statusResult);
      setLlmModels(models);
      setLlmModel((current) => {
        if (current && modelNames.includes(current)) {
          return current;
        }
        return statusResult.default_model || modelNames[0] || "";
      });
      setDeepseekApiKeyConfigured(Boolean(deepseekStatus.configured));
    } catch (requestError) {
      if (!isActive()) {
        return;
      }
      setLlmStatus({
        available: false,
        error: requestError.message
      });
      setLlmModels([]);
      setLlmModel("");
    } finally {
      if (isActive()) {
        setLlmStatusRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    let active = true;

    refreshLlmStatus(() => active);

    return () => {
      active = false;
    };
  }, [refreshLlmStatus]);

  useEffect(() => {
    return () => {
      if (longWaitTimerRef.current) {
        window.clearTimeout(longWaitTimerRef.current);
      }
      if (llmAbortControllerRef.current) {
        llmAbortControllerRef.current.abort();
      }
    };
  }, []);

  useEffect(() => {
    if (activeTab !== "chat" || !chatScrollRef.current) {
      return;
    }
    chatScrollRef.current.scrollTo({
      top: chatScrollRef.current.scrollHeight,
      behavior: "smooth"
    });
  }, [activeTab, llmHistory, llmLoading, streamAnswer, llmStage]);

  function resetLlmProgress() {
    if (longWaitTimerRef.current) {
      window.clearTimeout(longWaitTimerRef.current);
      longWaitTimerRef.current = null;
    }
    setLlmStage("");
    setLongWaitHint("");
    setStreamAnswer("");
    streamAnswerRef.current = "";
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
    // Only send the visible chat-window history; clearChat() resets this state.
    const requestHistory = llmHistory.map((item) => ({
      role: item.role,
      content: item.content
    }));
    const abortController = new AbortController();
    llmAbortControllerRef.current = abortController;

    setLlmLoading(true);
    setLlmError("");
    setLlmQuestion("");
    resetLlmProgress();
    setLlmHistory((current) => [...current, { role: "user", content: userMessage }]);
    setLlmStage(llmHistory.length === 0 && userMessage.length <= 8 ? "fast_path" : "interpretation");
    longWaitTimerRef.current = window.setTimeout(() => {
      setLongWaitHint("本地模型响应较慢。可以继续等待，也可以稍后重试。");
    }, LONG_WAIT_MS);

    try {
      const result = await askLlmStream(
        {
          message: userMessage,
          model: llmModel || undefined,
          selected_recipe_id: null,
          top_k: llmTopK,
          history: requestHistory,
          show_reasoning: false,
          use_deepseek_interpretation: useDeepseekInterpretation,
          allow_external_rerank: allowExternalRerank
        },
        {
          onEvent: (event) => {
            if (event.type === "stage") {
              setLlmStage(event.stage || "");
            } else if (event.type === "interpretation") {
              setStreamInterpretation(event.data || null);
            } else if (event.type === "retrieval") {
              setStreamRetrieval(event.data || null);
            } else if (event.type === "answer_chunk") {
              setStreamAnswer((current) => {
                const next = current + (event.delta || "");
                streamAnswerRef.current = next;
                return next;
              });
            }
          },
          signal: abortController.signal
        }
      );

      setLlmHistory((current) => [...current, { role: "assistant", content: result.answer }]);
      setLlmResult(result);
      setLlmQuestion("");
      setStreamInterpretation(result.interpretation || null);
      setStreamRetrieval(result.retrieval || null);
      setStreamAnswer(result.answer || "");
      streamAnswerRef.current = result.answer || "";
      setLlmStage(result.pipeline?.mode === "fast_path" ? "fast_path" : "answer");
      setLongWaitHint("");
    } catch (requestError) {
      if (requestError.name === "AbortError" || abortController.signal.aborted) {
        setLlmHistory((current) => [
          ...current,
          {
            role: "assistant",
            content: `${streamAnswerRef.current || "本轮生成已停止。"}\n\n[已停止]`
          }
        ]);
        setLongWaitHint("");
      } else {
        setLlmError(requestError.message);
      }
      setLlmStage("");
    } finally {
      if (llmAbortControllerRef.current === abortController) {
        llmAbortControllerRef.current = null;
      }
      if (longWaitTimerRef.current) {
        window.clearTimeout(longWaitTimerRef.current);
        longWaitTimerRef.current = null;
      }
      setLlmLoading(false);
    }
  }

  function stopLlmQuestion() {
    if (llmAbortControllerRef.current) {
      llmAbortControllerRef.current.abort();
    }
  }

  function clearChat() {
    setLlmHistory([]);
    setLlmResult(null);
    setLlmError("");
    resetLlmProgress();
  }

  function handleDeepseekOptionChange(option, checked, event) {
    if (checked && !deepseekApiKeyConfigured) {
      const targetRect = event.currentTarget.getBoundingClientRect();
      const popoverWidth = 340;
      const popoverHeight = 230;
      setDeepseekNotice({
        x: Math.max(12, Math.min(targetRect.left + targetRect.width / 2 + 12, window.innerWidth - popoverWidth - 12)),
        y: Math.max(12, Math.min(targetRect.top - 8, window.innerHeight - popoverHeight - 12)),
        title: option === "interpretation" ? "DeepSeek前置解析未启用" : "DeepSeek后处理未启用",
        body: "当前没有配置 DeepSeek API Key。此开关不会启动外部调用；如需使用，请先到“管理 -> AI分析食材”中配置 Key。未配置时，相关工作由本地模型和本地检索完成。"
      });
      return;
    }
    if (option === "interpretation") {
      setUseDeepseekInterpretation(checked);
    } else {
      setAllowExternalRerank(checked);
    }
    const targetRect = event.currentTarget.getBoundingClientRect();
    const popoverWidth = 340;
    const popoverHeight = 230;
    const preferredX = targetRect.left + targetRect.width / 2 + 12;
    const preferredY = targetRect.top - 8;
    setDeepseekNotice({
      x: Math.max(12, Math.min(preferredX, window.innerWidth - popoverWidth - 12)),
      y: Math.max(12, Math.min(preferredY, window.innerHeight - popoverHeight - 12)),
      title: option === "interpretation" ? "DeepSeek前置解析" : "DeepSeek后处理",
      body: buildDeepseekNoticeText(option, checked)
    });
  }

  const total = searchResult?.total ?? 0;
  const currentStart = total === 0 ? 0 : searchOffset + 1;
  const currentEnd = Math.min(searchOffset + PAGE_SIZE, total);
  const canGoPrev = searchOffset > 0;
  const canGoNext = searchOffset + PAGE_SIZE < total;

  const llmModelOptions = useMemo(() => {
    const seen = new Set();
    const installedModelNames = llmModels.map((item) => item.name).filter(Boolean);
    const defaultModel =
      llmStatus?.default_model && installedModelNames.includes(llmStatus.default_model)
        ? llmStatus.default_model
        : "";
    return [defaultModel, ...installedModelNames].filter((item) => {
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
      <div className="ai-tabs" role="tablist" aria-label="智能问答功能切换">
        <button
          type="button"
          role="tab"
          className={activeTab === "chat" ? "ai-tab active" : "ai-tab"}
          aria-selected={activeTab === "chat"}
          onClick={() => setActiveTab("chat")}
        >
          AI问答
        </button>
        <button
          type="button"
          role="tab"
          className={activeTab === "search" ? "ai-tab active" : "ai-tab"}
          aria-selected={activeTab === "search"}
          onClick={() => setActiveTab("search")}
        >
          自然语言搜索
        </button>
      </div>

      {activeTab === "chat" ? (
        <section className="panel chatgpt-panel">
          {deepseekNotice ? (
            <div
              className="deepseek-privacy-popover"
              style={{ left: `${deepseekNotice.x}px`, top: `${deepseekNotice.y}px` }}
              role="dialog"
              aria-label={deepseekNotice.title}
            >
              <strong>{deepseekNotice.title}</strong>
              <p>{deepseekNotice.body}</p>
              <button type="button" className="mini-confirm-button" onClick={() => setDeepseekNotice(null)}>
                我知道了
              </button>
            </div>
          ) : null}
          <div className="chat-header">
            <div>
              {(displayedInterpretation || displayedRetrieval || llmResult) && !llmLoading ? (
                <button type="button" className="chat-debug-button header-debug-button" onClick={() => setShowDebugModal(true)}>
                  查看本轮检索与引用
                </button>
              ) : null}
              <h2>AI问答</h2>
            </div>
            <div className="chat-status-pill">
              <span>{llmStatus?.available ? "Ollama 已连接" : "Ollama 未连接"}</span>
              <strong>{llmModel || llmStatus?.default_model || "未发现模型"}</strong>
              {!llmStatus?.available ? (
                <button
                  type="button"
                  className="chat-status-retry"
                  onClick={() => refreshLlmStatus()}
                  disabled={llmStatusRefreshing}
                >
                  {llmStatusRefreshing ? "连接中..." : "重试连接"}
                </button>
              ) : null}
            </div>
          </div>

          {llmStatus?.error ? <div className="error-banner">{llmStatus.error}</div> : null}

          <div className="chat-feed" ref={chatScrollRef}>
            {llmHistory.length === 0 && !llmLoading ? (
              <div className="chat-empty">
                <h3>输入问题开始对话</h3>
                <p>可以直接闲聊，也可以询问菜谱、食材、做法、自动标签或筛选相关问题。</p>
              </div>
            ) : null}

            {llmHistory.map((item, index) => (
              <ChatBubble key={`${item.role}-${index}`} item={item} />
            ))}

            {llmLoading ? (
              <StreamingAssistantBubble
                stage={llmStage}
                answer={streamAnswer}
                showReasoning={showReasoning}
                longWaitHint={longWaitHint}
              />
            ) : null}
          </div>

          {llmError ? <div className="error-banner">{llmError}</div> : null}

          {showDebugModal ? (
            <div className="debug-modal-backdrop" role="presentation" onClick={() => setShowDebugModal(false)}>
              <section className="debug-modal-card" role="dialog" aria-modal="true" aria-label="本轮检索与引用" onClick={(event) => event.stopPropagation()}>
                <div className="debug-modal-header">
                  <div>
                    <p className="eyebrow">Retrieval Trace</p>
                    <h2>本轮检索与引用</h2>
                  </div>
                  <button type="button" className="debug-modal-close" onClick={() => setShowDebugModal(false)} aria-label="关闭">
                    ×
                  </button>
                </div>

                <div className="debug-modal-body">
                  <section className="debug-block">
                    <h3>概念解释</h3>
                    {displayedInterpretation ? (
                      <>
                        <div className="debug-stat-grid">
                          <div className="debug-stat">
                            <span>来源</span>
                            <strong>
                              {interpretationSourceLabel(displayedInterpretation.source)}
                            </strong>
                          </div>
                          <div className="debug-stat">
                            <span>检索短句</span>
                            <strong>{displayedRetrieval?.query || displayedInterpretation.retrieval_query || "-"}</strong>
                          </div>
                          <div className="debug-stat">
                            <span>执行模式</span>
                            <strong>{llmResult?.pipeline?.mode === "fast_path" ? "快速回复" : llmResult?.pipeline?.mode === "general_chat" ? "普通问答" : "检索增强"}</strong>
                          </div>
                        </div>
                        <UnderstandingTags
                          understanding={{
                            free_text_terms: displayedInterpretation.concepts || [],
                            include_ingredients: displayedInterpretation.expanded_terms || [],
                            exclude_ingredients: displayedInterpretation.constraints || []
                          }}
                        />
                        {displayedInterpretation.intent ? <p className="recipe-meta">意图：{displayedInterpretation.intent}</p> : null}
                        {displayedInterpretation.notes ? <p className="recipe-meta">备注：{displayedInterpretation.notes}</p> : null}
                      </>
                    ) : (
                      <p>本轮没有概念解释信息。</p>
                    )}
                  </section>

                  {displayedRetrieval ? (
                    <section className="debug-block">
                      <h3>检索阶段</h3>
                      <div className="debug-stat-grid">
                        <div className="debug-stat">
                          <span>命中条目</span>
                          <strong>{displayedRetrieval.total ?? 0}</strong>
                        </div>
                        <div className="debug-stat">
                          <span>规则理解</span>
                          <strong>{Object.values(displayedRetrieval.understanding || {}).flat().length}</strong>
                        </div>
                      </div>
                      <UnderstandingTags understanding={displayedRetrieval.understanding} />
                      {displayedRetrieval.external_rerank?.enabled ? (
                        <div className="info-banner">
                          DeepSeek后处理：
                          {displayedRetrieval.external_rerank.source === "deepseek"
                            ? "已使用 DeepSeek 对脱敏候选摘要排序"
                            : displayedRetrieval.external_rerank.error || displayedRetrieval.external_rerank.notes || "未改变本地排序"}
                        </div>
                      ) : null}
                      {displayedRetrieval.items?.length ? (
                        <div className="debug-card-grid">
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
                    <section className="debug-block">
                      <h3>本轮引用</h3>
                      {llmResult.citations?.length ? (
                        <div className="debug-card-grid">
                          {llmResult.citations.map((item) => (
                            <RecipeRefCard key={`citation-${item.id}-${item.source || "citation"}`} item={item} onOpenRecipe={onOpenRecipe} />
                          ))}
                        </div>
                      ) : (
                        <p>本轮没有引用到可展示的条目。</p>
                      )}
                    </section>
                  ) : null}
                </div>
              </section>
            </div>
          ) : null}

          <div className="chat-composer">
            <textarea
              id="llm-question"
              rows={2}
              placeholder="输入问题，Alt + Enter 发送"
              value={llmQuestion}
              onChange={(event) => setLlmQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.altKey && event.key === "Enter") {
                  event.preventDefault();
                  if (llmLoading || !llmQuestion.trim() || !llmStatus?.available) {
                    return;
                  }
                  runLlmQuestion();
                }
              }}
            />
            <div className="chat-composer-footer">
              <div className="chat-mini-controls">
                <label className="chat-mini-select">
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

                <label className="chat-mini-select">
                  <span>基础候选</span>
                  <select value={String(llmTopK)} onChange={(event) => setLlmTopK(Number(event.target.value))}>
                    {[4, 6, 8, 10].map((item) => (
                      <option key={item} value={String(item)}>
                        最低 Top {item}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="chat-mini-toggle">
                  <input
                    type="checkbox"
                    checked={showReasoning}
                    onChange={(event) => setShowReasoning(event.target.checked)}
                  />
                  <span>过程</span>
                </label>

                <label className="chat-mini-toggle" title="只把用户问题发送给 DeepSeek，用于解析需求，不发送菜谱内容。">
                  <input
                    type="checkbox"
                    checked={useDeepseekInterpretation}
                    onChange={(event) => handleDeepseekOptionChange("interpretation", event.target.checked, event)}
                  />
                  <span>{deepseekApiKeyConfigured ? "DeepSeek前置解析" : "DeepSeek前置解析（未配置Key）"}</span>
                </label>

                <label className="chat-mini-toggle" title="开启后才会把本地 Top 候选的脱敏摘要发给 DeepSeek 排序。默认关闭。">
                  <input
                    type="checkbox"
                    checked={allowExternalRerank}
                    onChange={(event) => handleDeepseekOptionChange("rerank", event.target.checked, event)}
                  />
                  <span>{deepseekApiKeyConfigured ? "DeepSeek后处理" : "DeepSeek后处理（未配置Key）"}</span>
                </label>
              </div>

              <div className="chat-composer-actions">
                {llmLoading ? (
                  <button
                    type="button"
                    className="action-button secondary"
                    onClick={stopLlmQuestion}
                  >
                    停止
                  </button>
                ) : null}
                <button
                  type="button"
                  className="action-button secondary"
                  onClick={clearChat}
                  disabled={llmLoading || llmHistory.length === 0}
                >
                  清空对话
                </button>
                <button
                  type="button"
                  className="action-button chat-send-button"
                  onClick={runLlmQuestion}
                  disabled={llmLoading || !llmQuestion.trim() || !llmStatus?.available}
                >
                  {llmLoading ? "生成中" : "发送"}
                </button>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === "search" ? (
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
                <UnderstandingTags understanding={searchResult.understanding} />
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
      ) : null}
    </div>
  );
}
