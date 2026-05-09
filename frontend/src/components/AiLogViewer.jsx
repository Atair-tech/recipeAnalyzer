import { useEffect, useState } from "react";

import { fetchAiLogDetail, fetchAiLogs } from "../lib/api";

const FEATURE_OPTIONS = [
  { value: "", label: "全部" },
  { value: "assistant_chat", label: "AI 问答" },
  { value: "managed_tagging", label: "自动标签" },
  { value: "import_refinement", label: "step1 本地AI分析食材" }
];

const STATUS_OPTIONS = [
  { value: "", label: "全部" },
  { value: "success", label: "成功" },
  { value: "error", label: "错误" }
];

function formatTitle(item) {
  const parts = [item.feature, item.stage];
  if (item.recipe_name) {
    parts.push(item.recipe_name);
  }
  return parts.filter(Boolean).join(" / ");
}

function replayBirthdayAnimation() {
  window.location.hash = "birthday";
}

export default function AiLogViewer() {
  const [feature, setFeature] = useState("");
  const [status, setStatus] = useState("");
  const [logs, setLogs] = useState([]);
  const [selectedLogId, setSelectedLogId] = useState(null);
  const [selectedLog, setSelectedLog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadLogs() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchAiLogs({ feature, status, limit: 100, offset: 0 });
        if (!active) {
          return;
        }
        setLogs(data.items || []);
        setSelectedLogId((current) => {
          if (current && data.items?.some((item) => item.id === current)) {
            return current;
          }
          return data.items?.[0]?.id || null;
        });
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadLogs();

    return () => {
      active = false;
    };
  }, [feature, status]);

  useEffect(() => {
    let active = true;

    async function loadDetail() {
      if (!selectedLogId) {
        setSelectedLog(null);
        return;
      }

      setDetailLoading(true);
      setError("");
      try {
        const data = await fetchAiLogDetail(selectedLogId);
        if (active) {
          setSelectedLog(data);
        }
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
  }, [selectedLogId]);

  return (
    <section className="panel">
      {error ? <div className="error-banner">{error}</div> : null}

      <div className="panel-header">
        <div>
          <p className="eyebrow">AI logs</p>
          <h2>AI 对话记录</h2>
        </div>
        <button type="button" className="action-button secondary" onClick={replayBirthdayAnimation}>
          重播生日动画
        </button>
      </div>

      <div className="filter-bar analytics-filter-bar">
        <label className="filter-shell">
          <span>功能</span>
          <select value={feature} onChange={(event) => setFeature(event.target.value)}>
            {FEATURE_OPTIONS.map((item) => (
              <option key={item.value || "all"} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-shell">
          <span>状态</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            {STATUS_OPTIONS.map((item) => (
              <option key={item.value || "all"} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="history-layout database-layout">
        <div className="history-list">
          {loading ? (
            <div className="empty-state compact-empty-state">
              <h3>加载中</h3>
            </div>
          ) : logs.length === 0 ? (
            <div className="empty-state compact-empty-state">
              <h3>暂无记录</h3>
            </div>
          ) : (
            logs.map((item) => (
              <button
                key={item.id}
                type="button"
                className={selectedLogId === item.id ? "history-card active" : "history-card"}
                onClick={() => setSelectedLogId(item.id)}
              >
                <div className="history-card-header">
                  <span>#{item.id}</span>
                  <span>{item.status}</span>
                </div>
                <h3>{formatTitle(item)}</h3>
                <p>{item.model}</p>
                <p>{item.created_at}</p>
              </button>
            ))
          )}
        </div>

        <div className="history-detail">
          {detailLoading ? (
            <div className="empty-state compact-empty-state">
              <h3>加载中</h3>
            </div>
          ) : !selectedLog ? (
            <div className="empty-state compact-empty-state">
              <h3>请选择一条记录</h3>
            </div>
          ) : (
            <>
              <div className="detail-grid detail-grid-wide">
                <div className="detail-stat">
                  <span>功能</span>
                  <strong>{selectedLog.feature}</strong>
                </div>
                <div className="detail-stat">
                  <span>阶段</span>
                  <strong>{selectedLog.stage || "-"}</strong>
                </div>
                <div className="detail-stat">
                  <span>状态</span>
                  <strong>{selectedLog.status}</strong>
                </div>
                <div className="detail-stat">
                  <span>模型</span>
                  <strong>{selectedLog.model}</strong>
                </div>
                <div className="detail-stat">
                  <span>任务 ID</span>
                  <strong>{selectedLog.run_id || "-"}</strong>
                </div>
                <div className="detail-stat">
                  <span>菜谱</span>
                  <strong>{selectedLog.recipe_name || selectedLog.recipe_id || "-"}</strong>
                </div>
              </div>

              <section className="detail-section">
                <h3>请求消息</h3>
                {selectedLog.request_messages?.length ? (
                  <div className="ai-log-message-list">
                    {selectedLog.request_messages.map((message, index) => (
                      <article key={`${selectedLog.id}-message-${index}`} className="ai-log-message-card">
                        <div className="ai-log-message-header">
                          <strong>{message.role}</strong>
                        </div>
                        <pre className="raw-text-block">{message.content}</pre>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p>无请求消息。</p>
                )}
              </section>

              <section className="detail-section">
                <h3>模型回复</h3>
                <pre className="raw-text-block">{selectedLog.response_text || "无"}</pre>
              </section>

              {selectedLog.error_text ? (
                <section className="detail-section">
                  <h3>错误</h3>
                  <pre className="raw-text-block">{selectedLog.error_text}</pre>
                </section>
              ) : null}

              {selectedLog.meta && Object.keys(selectedLog.meta).length > 0 ? (
                <section className="detail-section">
                  <h3>元数据</h3>
                  <pre className="raw-text-block">{JSON.stringify(selectedLog.meta, null, 2)}</pre>
                </section>
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
