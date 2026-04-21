import { useEffect, useMemo, useState } from "react";

import {
  fetchImportRefineStatus,
  fetchLlmModels,
  pauseImportRefineRun,
  resumeImportRefineRun,
  startImportRefineRun
} from "../lib/api";

export default function ImportRefinementPanel() {
  const [runStatus, setRunStatus] = useState(null);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;

    async function loadData() {
      try {
        const [statusData, modelData] = await Promise.all([
          fetchImportRefineStatus(),
          fetchLlmModels()
        ]);
        if (!active) {
          return;
        }
        setRunStatus(statusData.run || null);
        setModels(modelData.items || []);
        setSelectedModel((current) => current || modelData.items?.[0]?.name || "");
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

    loadData();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const statusData = await fetchImportRefineStatus();
        setRunStatus(statusData.run || null);
      } catch (requestError) {
        setError(requestError.message);
      }
    }, 2500);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const progressText = useMemo(() => {
    if (!runStatus) {
      return "0 / 0";
    }
    return `${runStatus.processed_count ?? 0} / ${runStatus.total_count ?? 0}`;
  }, [runStatus]);

  async function handleStartRun() {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await startImportRefineRun(selectedModel || undefined);
      setRunStatus(result.run || null);
      setMessage("AI 精校任务已启动。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function handlePauseRun() {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await pauseImportRefineRun();
      setRunStatus(result.run || null);
      setMessage("AI 精校任务已请求暂停。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function handleResumeRun() {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await resumeImportRefineRun();
      setRunStatus(result.run || null);
      setMessage("AI 精校任务已恢复。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="panel">
      {error ? <div className="error-banner">{error}</div> : null}
      {message ? <div className="warning-banner">{message}</div> : null}

      <div className="panel-header">
        <div>
          <p className="eyebrow">AI refinement</p>
          <h2>AI 精校切分结果</h2>
        </div>
      </div>

      <div className="warning-banner">
        这个任务会对当前菜谱的
        {" "}
        <code>食材 / 调料 / 结构化食材 / 做法及要点 / 备注</code>
        {" "}
        做本地 LLM 精校，并直接更新数据库。增量逻辑基于
        {" "}
        <code>source_hash + model + refine_version</code>
        ，未变化记录会自动跳过。
      </div>

      <div className="detail-grid detail-grid-wide">
        <div className="detail-stat">
          <span>当前进度</span>
          <strong>{progressText}</strong>
        </div>
        <div className="detail-stat">
          <span>本轮状态</span>
          <strong>{runStatus?.status || "未启动"}</strong>
        </div>
        <div className="detail-stat">
          <span>已精校</span>
          <strong>{runStatus?.refined_count ?? 0}</strong>
        </div>
        <div className="detail-stat">
          <span>跳过数量</span>
          <strong>{runStatus?.skipped_count ?? 0}</strong>
        </div>
        <div className="detail-stat">
          <span>错误数量</span>
          <strong>{runStatus?.error_count ?? 0}</strong>
        </div>
        <div className="detail-stat">
          <span>模型</span>
          <strong>{runStatus?.model || selectedModel || "-"}</strong>
        </div>
      </div>

      <div className="filter-bar">
        <label className="filter-shell">
          <span>模型</span>
          <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} disabled={loading}>
            {models.map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="action-row">
        <button type="button" className="action-button" onClick={handleStartRun} disabled={working || loading}>
          开启 AI 精校
        </button>
        <button
          type="button"
          className="action-button secondary"
          onClick={handlePauseRun}
          disabled={working || runStatus?.status !== "running"}
        >
          暂停
        </button>
        <button
          type="button"
          className="action-button secondary"
          onClick={handleResumeRun}
          disabled={working || runStatus?.status !== "paused"}
        >
          恢复
        </button>
      </div>

      {runStatus?.error_message ? (
        <section className="detail-section">
          <h3>最近错误</h3>
          <p>{runStatus.error_message}</p>
        </section>
      ) : null}
    </section>
  );
}
