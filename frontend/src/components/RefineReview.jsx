import { useEffect, useMemo, useState } from "react";

import {
  fetchLlmModels,
  fetchRefineReviewDetail,
  fetchRefineReviewItems,
  rerunRefineReview,
  updateRefineReview
} from "../lib/api";

const ISSUE_TYPE_OPTIONS = [
  { value: "", label: "全部原因" },
  { value: "model_empty", label: "模型未抽出食材" },
  { value: "model_format", label: "模型输出格式不稳" },
  { value: "postprocess_strict", label: "后处理过滤过严" },
  { value: "source_dirty", label: "原始文本过脏" },
  { value: "unknown", label: "待判断" }
];

function formatIngredientAmount(item) {
  const amountPart = [item.amount, item.unit].filter(Boolean).join("");
  const remarkPart = item.remark ? ` / ${item.remark}` : "";
  if (!amountPart) {
    return item.remark || "未指定用量";
  }
  return `${amountPart}${remarkPart}`;
}

function reviewStatusLabel(status) {
  if (status === "approved") {
    return "已确认";
  }
  if (status === "issue") {
    return "有问题";
  }
  return "待审查";
}

function issueTypeLabel(issueType) {
  return ISSUE_TYPE_OPTIONS.find((item) => item.value === issueType)?.label || "未分类";
}

function IngredientList({ items, emptyText }) {
  if (!items?.length) {
    return <p>{emptyText}</p>;
  }

  return (
    <div className="suggestion-list">
      {items.map((item, index) => (
        <article key={`${item.name}-${index}`} className="detail-stat suggestion-card">
          <span>{item.name}</span>
          <strong>{formatIngredientAmount(item)}</strong>
        </article>
      ))}
    </div>
  );
}

export default function RefineReview() {
  const [items, setItems] = useState([]);
  const [selectedRecipeId, setSelectedRecipeId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("error");
  const [issueTypeFilter, setIssueTypeFilter] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [issueTypeDraft, setIssueTypeDraft] = useState("");

  async function loadList() {
    setListLoading(true);
    setError("");
    try {
      const [listResult, modelResult] = await Promise.all([
        fetchRefineReviewItems({
          search: search.trim(),
          status: statusFilter,
          issueType: issueTypeFilter,
          limit: 200
        }),
        fetchLlmModels()
      ]);
      setItems(listResult.items || []);
      setModels(modelResult.items || []);
      setSelectedModel((current) => current || modelResult.items?.[0]?.name || "");
      setSelectedRecipeId((current) => {
        if (current && (listResult.items || []).some((item) => item.id === current)) {
          return current;
        }
        return listResult.items?.[0]?.id ?? null;
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    loadList();
  }, [statusFilter, issueTypeFilter]);

  useEffect(() => {
    let active = true;

    async function loadDetail() {
      if (!selectedRecipeId) {
        setDetail(null);
        setNoteDraft("");
        setIssueTypeDraft("");
        return;
      }

      setDetailLoading(true);
      setError("");
      try {
        const result = await fetchRefineReviewDetail(selectedRecipeId);
        if (!active) {
          return;
        }
        setDetail(result);
        setNoteDraft(result.review?.note || "");
        setIssueTypeDraft(result.review?.issue_type || result.derived_issue_type || "");
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      } finally {
        if (active) {
          setDetailLoading(false);
        }
      }
    }

    loadDetail();

    return () => {
      active = false;
    };
  }, [selectedRecipeId]);

  const summary = useMemo(() => {
    return items.reduce(
      (accumulator, item) => {
        accumulator.total += 1;
        if (item.review_status === "approved") {
          accumulator.approved += 1;
        } else if (item.review_status === "issue") {
          accumulator.issue += 1;
        } else {
          accumulator.pending += 1;
        }
        if (item.last_error) {
          accumulator.error += 1;
        }
        return accumulator;
      },
      { total: 0, pending: 0, approved: 0, issue: 0, error: 0 }
    );
  }, [items]);

  async function handleMark(status) {
    if (!selectedRecipeId) {
      return;
    }
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await updateRefineReview(selectedRecipeId, {
        status,
        issue_type: status === "issue" ? issueTypeDraft || null : null,
        note: noteDraft
      });
      setDetail(result);
      setIssueTypeDraft(result.review?.issue_type || result.derived_issue_type || "");
      setItems((current) =>
        current.map((item) =>
          item.id === selectedRecipeId
            ? {
                ...item,
                review_status: result.review.status,
                issue_type: result.review.issue_type || result.derived_issue_type || "",
                review_note: result.review.note,
                review_updated_at: result.review.updated_at
              }
            : item
        )
      );
      setMessage(status === "approved" ? "已标记为通过。" : "已标记为有问题。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function handleRerun() {
    if (!selectedRecipeId) {
      return;
    }
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await rerunRefineReview(selectedRecipeId, selectedModel || undefined);
      setDetail(result);
      setNoteDraft(result.review?.note || "");
      setIssueTypeDraft(result.review?.issue_type || result.derived_issue_type || "");
      setItems((current) =>
        current.map((item) =>
          item.id === selectedRecipeId
            ? {
                ...item,
                refine_model: result.refine_state?.model || item.refine_model,
                refine_version: result.refine_state?.refine_version || item.refine_version,
                refined_at: result.refine_state?.refined_at || item.refined_at,
                last_error: result.refine_state?.last_error || "",
                last_raw_response: result.refine_state?.last_raw_response || "",
                issue_type: result.review?.issue_type || result.derived_issue_type || "",
                ingredient_count: result.recipe?.ingredients?.length ?? item.ingredient_count
              }
            : item
        )
      );
      setMessage("已按当前模型重新精校该条菜谱。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="section-stack">
      {error ? <div className="error-banner">{error}</div> : null}
      {message ? <div className="success-banner">{message}</div> : null}

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Refine Failure Workbench</p>
            <h2>食材精校失败样本</h2>
          </div>
        </div>

        <div className="detail-grid detail-grid-wide">
          <div className="detail-stat">
            <span>当前列表</span>
            <strong>{summary.total}</strong>
          </div>
          <div className="detail-stat">
            <span>失败样本</span>
            <strong>{summary.error}</strong>
          </div>
          <div className="detail-stat">
            <span>待审查</span>
            <strong>{summary.pending}</strong>
          </div>
          <div className="detail-stat">
            <span>已确认</span>
            <strong>{summary.approved}</strong>
          </div>
          <div className="detail-stat">
            <span>已标问题</span>
            <strong>{summary.issue}</strong>
          </div>
        </div>

        <div className="filter-bar filter-bar-wide">
          <label className="search-shell">
            <span>搜索</span>
            <input
              type="search"
              placeholder="搜索菜名、专题库或分组"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  loadList();
                }
              }}
            />
          </label>
          <label className="filter-shell">
            <span>状态</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="error">仅失败</option>
              <option value="all">全部</option>
              <option value="pending">待审查</option>
              <option value="approved">已确认</option>
              <option value="issue">有问题</option>
            </select>
          </label>
          <label className="filter-shell">
            <span>失败类型</span>
            <select value={issueTypeFilter} onChange={(event) => setIssueTypeFilter(event.target.value)}>
              {ISSUE_TYPE_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="action-button secondary" onClick={loadList} disabled={listLoading || working}>
            刷新列表
          </button>
        </div>
      </section>

      <div className="history-layout">
        <div className="history-list">
          {listLoading ? <p className="recipe-meta">正在加载失败样本列表...</p> : null}
          {!listLoading &&
            items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={selectedRecipeId === item.id ? "history-card active" : "history-card"}
                onClick={() => setSelectedRecipeId(item.id)}
              >
                <div className="history-card-header">
                  <strong>{item.name}</strong>
                  <span>{item.ingredient_count} 项</span>
                </div>
                <p>{[item.library_section, item.section_name].filter(Boolean).join(" / ") || "未归类"}</p>
                <div className="tag-row compact-tag-row">
                  <span className="tag">{reviewStatusLabel(item.review_status)}</span>
                  {item.issue_type ? <span className="tag muted">{issueTypeLabel(item.issue_type)}</span> : null}
                  {item.last_error ? <span className="tag muted">失败</span> : null}
                </div>
              </button>
            ))}
          {!listLoading && items.length === 0 ? (
            <div className="empty-state compact-empty-state">
              <h3>没有匹配结果</h3>
              <p>可以调整搜索词或筛选条件。</p>
            </div>
          ) : null}
        </div>

        <div className="history-detail">
          {!selectedRecipeId ? (
            <div className="empty-state compact-empty-state">
              <h3>未选择条目</h3>
              <p>从左侧选择一条失败样本开始审查。</p>
            </div>
          ) : null}

          {selectedRecipeId && detailLoading ? (
            <div className="empty-state compact-empty-state">
              <h3>正在读取详情</h3>
            </div>
          ) : null}

          {selectedRecipeId && !detailLoading && detail ? (
            <div className="section-stack">
              <section className="panel">
                <div className="panel-header">
                  <div>
                    <p className="eyebrow">Failure Detail</p>
                    <h2>{detail.recipe.name}</h2>
                    <p className="recipe-meta">
                      {[detail.recipe.library_section, detail.recipe.section_name, detail.recipe.cuisine]
                        .filter(Boolean)
                        .join(" / ")}
                    </p>
                  </div>
                  <div className="tag-row compact-tag-row">
                    <span className="tag">{reviewStatusLabel(detail.review.status)}</span>
                    {detail.review.issue_type || detail.derived_issue_type ? (
                      <span className="tag muted">{issueTypeLabel(detail.review.issue_type || detail.derived_issue_type)}</span>
                    ) : null}
                    {detail.refine_state?.model ? <span className="tag muted">{detail.refine_state.model}</span> : null}
                  </div>
                </div>

                <div className="import-summary-grid import-summary-grid-wide">
                  <div className="detail-stat">
                    <span>精校时间</span>
                    <strong>{detail.refine_state?.refined_at || "未精校"}</strong>
                  </div>
                  <div className="detail-stat">
                    <span>精校版本</span>
                    <strong>{detail.refine_state?.refine_version || "-"}</strong>
                  </div>
                  <div className="detail-stat">
                    <span>结构化项数</span>
                    <strong>{detail.recipe.ingredients.length}</strong>
                  </div>
                  <div className="detail-stat">
                    <span>最近快照</span>
                    <strong>{detail.snapshot?.created_at || "无"}</strong>
                  </div>
                </div>

                {detail.refine_state?.last_error ? (
                  <section className="detail-section">
                    <h3>最近错误</h3>
                    <p>{detail.refine_state.last_error}</p>
                  </section>
                ) : null}

                {detail.refine_state?.last_raw_response ? (
                  <section className="detail-section">
                    <h3>模型原始输出</h3>
                    <pre className="stream-box">{detail.refine_state.last_raw_response}</pre>
                  </section>
                ) : null}

                <section className="detail-section">
                  <h3>原始食材文本</h3>
                  <pre className="stream-box">{detail.recipe.ingredients_text || "未填写"}</pre>
                </section>

                {detail.snapshot ? (
                  <>
                    <section className="detail-section">
                      <h3>精校前结构化食材</h3>
                      <IngredientList
                        items={detail.snapshot.before_ingredients}
                        emptyText="快照中没有精校前结构化食材。"
                      />
                    </section>

                    <section className="detail-section">
                      <h3>精校后结构化食材</h3>
                      <IngredientList
                        items={detail.snapshot.after_ingredients}
                        emptyText="快照中没有精校后结构化食材。"
                      />
                    </section>
                  </>
                ) : null}

                <section className="detail-section">
                  <h3>当前结构化食材</h3>
                  <IngredientList items={detail.recipe.ingredients} emptyText="当前没有结构化食材。" />
                </section>

                <div className="mapping-grid">
                  <label className="filter-shell">
                    <span>失败分类</span>
                    <select value={issueTypeDraft} onChange={(event) => setIssueTypeDraft(event.target.value)}>
                      {ISSUE_TYPE_OPTIONS.slice(1).map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="filter-shell">
                    <span>单条重跑模型</span>
                    <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
                      {models.map((item) => (
                        <option key={item.name} value={item.name}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <section className="detail-section">
                  <h3>审查备注</h3>
                  <textarea
                    rows={4}
                    value={noteDraft}
                    onChange={(event) => setNoteDraft(event.target.value)}
                    placeholder="记录失败模式、规则建议或人工判断。"
                  />
                </section>

                <div className="action-row">
                  <button type="button" className="action-button" onClick={() => handleMark("approved")} disabled={working}>
                    标记通过
                  </button>
                  <button type="button" className="action-button secondary" onClick={() => handleMark("issue")} disabled={working}>
                    标记有问题
                  </button>
                  <button type="button" className="action-button secondary" onClick={handleRerun} disabled={working}>
                    单条重跑精校
                  </button>
                </div>
              </section>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
