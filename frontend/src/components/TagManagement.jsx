import { useEffect, useMemo, useState } from "react";

import {
  createManagedTag,
  deleteManagedTag,
  fetchLlmModels,
  fetchManagedTags,
  fetchTaggingStatus,
  pauseTaggingRun,
  resumeTaggingRun,
  startTaggingRun,
  updateManagedTag
} from "../lib/api";

const EMPTY_FORM = {
  name: "",
  description: "",
  is_active: true,
  sort_order: 0
};

export default function TagManagement() {
  const [tags, setTags] = useState([]);
  const [runStatus, setRunStatus] = useState(null);
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingTagId, setEditingTagId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;

    async function loadData() {
      try {
        const [tagData, statusData, modelData] = await Promise.all([
          fetchManagedTags(),
          fetchTaggingStatus(),
          fetchLlmModels()
        ]);

        if (!active) {
          return;
        }

        setTags(tagData.items || []);
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
        const statusData = await fetchTaggingStatus();
        setRunStatus(statusData.run || null);
      } catch (requestError) {
        setError(requestError.message);
      }
    }, 2500);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  async function refreshAll() {
    const [tagData, statusData] = await Promise.all([fetchManagedTags(), fetchTaggingStatus()]);
    setTags(tagData.items || []);
    setRunStatus(statusData.run || null);
  }

  function resetForm() {
    setForm(EMPTY_FORM);
    setEditingTagId(null);
  }

  function startEdit(tag) {
    setEditingTagId(tag.id);
    setForm({
      name: tag.name,
      description: tag.description || "",
      is_active: Boolean(tag.is_active),
      sort_order: tag.sort_order ?? 0
    });
  }

  async function submitTag(event) {
    event.preventDefault();
    setWorking(true);
    setError("");
    setMessage("");

    try {
      if (editingTagId) {
        await updateManagedTag(editingTagId, form);
        setMessage("标签已更新。");
      } else {
        await createManagedTag(form);
        setMessage("标签已创建。");
      }

      await refreshAll();
      resetForm();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function removeTag(tagId) {
    setWorking(true);
    setError("");
    setMessage("");

    try {
      await deleteManagedTag(tagId);
      await refreshAll();

      if (editingTagId === tagId) {
        resetForm();
      }

      setMessage("标签已删除。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function handleStartRun() {
    setWorking(true);
    setError("");
    setMessage("");

    try {
      const result = await startTaggingRun(selectedModel || undefined);
      setRunStatus(result.run || null);
      setMessage("本地 AI 打标签任务已启动。");
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
      const result = await pauseTaggingRun();
      setRunStatus(result.run || null);
      setMessage("任务已请求暂停。");
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
      const result = await resumeTaggingRun();
      setRunStatus(result.run || null);
      setMessage("任务已恢复。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  const progressText = useMemo(() => {
    if (!runStatus) {
      return "0 / 0";
    }
    return `${runStatus.processed_count ?? 0} / ${runStatus.total_count ?? 0}`;
  }, [runStatus]);

  return (
    <div className="section-stack">
      {error ? <div className="error-banner">{error}</div> : null}
      {message ? <div className="warning-banner">{message}</div> : null}

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Managed tags</p>
            <h2>标签管理</h2>
          </div>
        </div>

        <div className="detail-grid detail-grid-wide">
          <div className="detail-stat">
            <span>标签数</span>
            <strong>{tags.length}</strong>
          </div>
          <div className="detail-stat">
            <span>当前进度</span>
            <strong>{progressText}</strong>
          </div>
          <div className="detail-stat">
            <span>本轮状态</span>
            <strong>{runStatus?.status || "未启动"}</strong>
          </div>
          <div className="detail-stat">
            <span>跳过数量</span>
            <strong>{runStatus?.skipped_count ?? 0}</strong>
          </div>
          <div className="detail-stat">
            <span>已打标签</span>
            <strong>{runStatus?.tagged_count ?? 0}</strong>
          </div>
          <div className="detail-stat">
            <span>错误数量</span>
            <strong>{runStatus?.error_count ?? 0}</strong>
          </div>
        </div>

        <div className="filter-bar">
          <label className="filter-shell">
            <span>模型</span>
            <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
              {models.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="action-row">
          <button type="button" className="action-button" onClick={handleStartRun} disabled={working}>
            启动本地 AI 打标签
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

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Tag catalog</p>
            <h2>{editingTagId ? "编辑标签" : "新增标签"}</h2>
          </div>
        </div>

        <form className="section-stack" onSubmit={submitTag}>
          <label className="search-shell">
            <span>标签名</span>
            <input
              type="text"
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
          </label>

          <label className="search-shell">
            <span>说明</span>
            <textarea
              rows={3}
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            />
          </label>

          <div className="filter-bar">
            <label className="filter-shell">
              <span>显示顺序</span>
              <input
                type="number"
                value={String(form.sort_order)}
                onChange={(event) =>
                  setForm((current) => ({ ...current, sort_order: Number(event.target.value) || 0 }))
                }
              />
            </label>
            <label className="filter-shell">
              <span>状态</span>
              <select
                value={form.is_active ? "active" : "inactive"}
                onChange={(event) =>
                  setForm((current) => ({ ...current, is_active: event.target.value === "active" }))
                }
              >
                <option value="active">启用</option>
                <option value="inactive">停用</option>
              </select>
            </label>
          </div>

          <div className="action-row">
            <button type="submit" className="action-button" disabled={working}>
              {editingTagId ? "保存标签" : "创建标签"}
            </button>
            <button type="button" className="action-button secondary" onClick={resetForm} disabled={working}>
              取消编辑
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Existing tags</p>
            <h2>现有标签</h2>
          </div>
        </div>

        {loading ? <p>加载中...</p> : null}
        {!loading ? (
          <div className="section-stack">
            {tags.map((tag) => (
              <article key={tag.id} className="history-card">
                <div className="panel-header">
                  <div>
                    <h3>{tag.name}</h3>
                    <p className="recipe-meta">{tag.description || "无说明"}</p>
                  </div>
                  <div className="tag-row compact-tag-row">
                    <span className="tag">{tag.is_active ? "启用" : "停用"}</span>
                    <span className="tag muted">显示顺序 {tag.sort_order}</span>
                    <span className="tag muted">命中 {tag.recipe_count}</span>
                  </div>
                </div>
                <div className="action-row">
                  <button
                    type="button"
                    className="action-button secondary"
                    onClick={() => startEdit(tag)}
                    disabled={working}
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    className="action-button secondary"
                    onClick={() => removeTag(tag.id)}
                    disabled={working}
                  >
                    删除
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
