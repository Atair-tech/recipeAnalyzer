import { useEffect, useMemo, useState } from "react";

import {
  fetchImportRefineStatus,
  fetchIngredientFilterStatus,
  fetchLlmModels,
  pauseImportRefineRun,
  resumeImportRefineRun,
  startImportRefineRun,
  pauseIngredientFilterRun,
  resumeIngredientFilterRun,
  saveDeepseekApiKey,
  startIngredientFilterRun,
} from "../lib/api";

const DEFAULT_INGREDIENT_FILTER_PROVIDERS = [
  { id: "deepseek_api", label: "DeepSeek API（默认）" },
  { id: "ollama", label: "本地 Ollama（备选）" },
];

export default function ImportRefinementPanel() {
  const [runStatus, setRunStatus] = useState(null);
  const [ingredientFilterStatus, setIngredientFilterStatus] = useState(null);
  const [ingredientFilterIsRunning, setIngredientFilterIsRunning] = useState(false);
  const [ingredientFilterPauseRequested, setIngredientFilterPauseRequested] = useState(false);
  const [ingredientFilterProviders, setIngredientFilterProviders] = useState(DEFAULT_INGREDIENT_FILTER_PROVIDERS);
  const [deepseekApiKeyConfigured, setDeepseekApiKeyConfigured] = useState(false);
  const [deepseekApiKeySource, setDeepseekApiKeySource] = useState("");
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [ingredientFilterProvider, setIngredientFilterProvider] = useState("deepseek_api");
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [apiKeySaving, setApiKeySaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadData() {
    const [refineStatusData, ingredientStatusData, modelData] = await Promise.all([
      fetchImportRefineStatus(),
      fetchIngredientFilterStatus(),
      fetchLlmModels(),
    ]);

    setRunStatus(refineStatusData.run || null);
    setIngredientFilterStatus(ingredientStatusData.run || null);
    setIngredientFilterIsRunning(Boolean(ingredientStatusData.is_running));
    setIngredientFilterPauseRequested(Boolean(ingredientStatusData.pause_requested));
    setIngredientFilterProviders(ingredientStatusData.available_providers || DEFAULT_INGREDIENT_FILTER_PROVIDERS);
    setDeepseekApiKeyConfigured(Boolean(ingredientStatusData.deepseek_api_key_configured));
    setDeepseekApiKeySource(ingredientStatusData.deepseek_api_key_source || "");
    setModels(modelData.items || []);
    setSelectedModel((current) => current || modelData.items?.[0]?.name || "");
  }

  useEffect(() => {
    let active = true;

    async function bootstrap() {
      try {
        await loadData();
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

    bootstrap();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const [refineStatusData, ingredientStatusData] = await Promise.all([
          fetchImportRefineStatus(),
          fetchIngredientFilterStatus(),
        ]);
        setRunStatus(refineStatusData.run || null);
        setIngredientFilterStatus(ingredientStatusData.run || null);
        setIngredientFilterIsRunning(Boolean(ingredientStatusData.is_running));
        setIngredientFilterPauseRequested(Boolean(ingredientStatusData.pause_requested));
        setIngredientFilterProviders(ingredientStatusData.available_providers || DEFAULT_INGREDIENT_FILTER_PROVIDERS);
        setDeepseekApiKeyConfigured(Boolean(ingredientStatusData.deepseek_api_key_configured));
        setDeepseekApiKeySource(ingredientStatusData.deepseek_api_key_source || "");
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

  const ingredientFilterProgressText = useMemo(() => {
    if (!ingredientFilterStatus) {
      return "0 / 0";
    }
    return `${ingredientFilterStatus.processed_count ?? 0} / ${ingredientFilterStatus.total_count ?? 0}`;
  }, [ingredientFilterStatus]);

  const ingredientFilterRunning = ingredientFilterIsRunning;
  const isDeepseekIngredientFilter =
    ingredientFilterStatus?.provider === "deepseek_api" || ingredientFilterProvider === "deepseek_api";

  async function handleStartRun() {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await startImportRefineRun(selectedModel || undefined);
      setRunStatus(result.run || null);
      setMessage("step1 本地AI分析食材任务已启动。");
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
      setMessage("step1 本地AI分析食材任务已请求暂停。");
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
      setMessage("step1 本地AI分析食材任务已恢复。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function handleStartIngredientFilterRun() {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      if (ingredientFilterRunning) {
        setMessage("当前已有 step2 外部AI剔除杂乱项任务正在运行，请等待完成或先暂停。");
        return;
      }
      if (ingredientFilterProvider === "deepseek_api" && !deepseekApiKeyConfigured) {
        setApiKeyInput("");
        setMessage("DeepSeek API Key 尚未配置。请输入 Key 后才会启动 step2，不会进行假运行。");
        setApiKeyModalOpen(true);
        return;
      }
      await startIngredientFilterRunWithCurrentProvider();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function startIngredientFilterRunWithCurrentProvider() {
    const result = await startIngredientFilterRun(
      ingredientFilterProvider === "ollama" ? selectedModel || undefined : undefined,
      ingredientFilterProvider
    );
    setIngredientFilterStatus(result.run || null);
    setIngredientFilterIsRunning(Boolean(result.is_running));
    setIngredientFilterPauseRequested(Boolean(result.pause_requested));
    setDeepseekApiKeyConfigured(Boolean(result.deepseek_api_key_configured));
    setDeepseekApiKeySource(result.deepseek_api_key_source || "");
    setMessage(
      ingredientFilterProvider === "deepseek_api"
        ? "step2 外部AI剔除杂乱项任务已启动。DeepSeek 返回前页面会持续显示运行状态。"
        : "step2 本地 Ollama 剔除杂乱项任务已启动。"
    );
  }

  async function handleSaveDeepseekApiKey(event) {
    event.preventDefault();
    const cleanApiKey = apiKeyInput.trim();
    if (!cleanApiKey) {
      setError("请输入 DeepSeek API Key。");
      return;
    }

    setApiKeySaving(true);
    setWorking(true);
    setError("");
    setMessage("");
    try {
      await saveDeepseekApiKey(cleanApiKey);
      setDeepseekApiKeyConfigured(true);
      setApiKeyModalOpen(false);
      setApiKeyInput("");
      await startIngredientFilterRunWithCurrentProvider();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setApiKeySaving(false);
      setWorking(false);
    }
  }

  async function handlePauseIngredientFilterRun() {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await pauseIngredientFilterRun();
      setIngredientFilterStatus(result.run || null);
      setIngredientFilterIsRunning(Boolean(result.is_running));
      setIngredientFilterPauseRequested(Boolean(result.pause_requested));
      setMessage("step2 外部AI剔除杂乱项任务已请求暂停。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorking(false);
    }
  }

  async function handleResumeIngredientFilterRun() {
    setWorking(true);
    setError("");
    setMessage("");
    try {
      const result = await resumeIngredientFilterRun();
      setIngredientFilterStatus(result.run || null);
      setIngredientFilterIsRunning(Boolean(result.is_running));
      setIngredientFilterPauseRequested(Boolean(result.pause_requested));
      setMessage("step2 外部AI剔除杂乱项任务已恢复。");
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
          <p className="eyebrow">Ingredient AI workflow</p>
          <h2>AI 分析食材</h2>
        </div>
      </div>

      <div className="warning-banner">
        step1 使用本地 AI 对每道菜的原始食材文本进行结构化分析，并更新数据库中的 <code>recipe_ingredients</code>
        结果。增量跳过逻辑基于 <code>食材分析输入hash + model + refine_version</code>，未变化记录会自动跳过。AI 生成结果仅供筛选、统计和推荐参考，原始 Excel 文本仍是最终依据。
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
          <span>已分析</span>
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
          启动 step1 本地AI分析食材
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

      {runStatus?.status === "running" ? (
        <div className="running-callout" role="status" aria-live="polite">
          <span className="running-dot" aria-hidden="true" />
          <div>
            <strong>step1 本地AI分析食材正在后台运行</strong>
            <p>
              可以切换到其他页面查看菜谱；只要后端服务不关闭，任务会继续运行。关闭浏览器页面通常不影响任务，但关闭后端窗口会中断任务，
              下次启动后会自动标记为暂停，可点击“恢复”继续。
            </p>
          </div>
        </div>
      ) : null}

      {runStatus?.error_message ? (
        <section className="detail-section">
          <h3>最近错误</h3>
          <p>{runStatus.error_message}</p>
        </section>
      ) : null}

      <section className="detail-section">
        <h3>step2. 外部AI剔除杂乱项</h3>
        <div className="detail-text-block">
          step2 默认使用 DeepSeek API 对全局食材候选词做二次清理，只发送食材候选词本身，不发送菜名、做法、备注或完整菜谱内容。
          本地 Ollama 保留为备选模式。被判定为杂乱项的内容会从菜谱库食材下拉菜单和总览统计中隐藏，但仍保留在数据库中，便于后续继续分析。
          清理结果仅用于显示和统计参考，不会删除数据库原始数据。
        </div>

        {ingredientFilterProvider === "deepseek_api" ? (
          <div className="inline-status-note">
            {deepseekApiKeyConfigured
              ? `DeepSeek API Key 已配置${deepseekApiKeySource ? `（来源：${deepseekApiKeySource}）` : ""}。`
              : "DeepSeek API Key 尚未配置。点击启动时会要求输入 Key；未输入前不会启动任务。"}
          </div>
        ) : null}

        {ingredientFilterRunning && isDeepseekIngredientFilter ? (
          <div className="running-callout" role="status" aria-live="polite">
            <span className="running-dot" aria-hidden="true" />
            <div>
              <strong>DeepSeek API 正在执行 step2 外部AI剔除杂乱项</strong>
              <p>
                已向外部模型提交候选食材列表，正在等待模型返回结果。一次性判断全部食材时可能需要几十秒到数分钟，
                期间请不要重复点击启动。可以切换到其他页面；只要后端服务不关闭，任务会继续运行。关闭后端窗口会中断任务，
                下次启动后会自动标记为暂停，可点击“恢复”继续。
              </p>
            </div>
          </div>
        ) : null}

        <div className="detail-grid detail-grid-wide">
          <div className="detail-stat">
            <span>当前进度</span>
            <strong>{ingredientFilterProgressText}</strong>
          </div>
          <div className="detail-stat">
            <span>本轮状态</span>
            <strong>
              {ingredientFilterIsRunning && ingredientFilterPauseRequested
                ? "正在暂停"
                : ingredientFilterIsRunning
                  ? "运行中"
                  : ingredientFilterStatus?.status || "未启动"}
            </strong>
          </div>
          <div className="detail-stat">
            <span>保留显示</span>
            <strong>{ingredientFilterStatus?.kept_count ?? 0}</strong>
          </div>
          <div className="detail-stat">
            <span>隐藏显示</span>
            <strong>{ingredientFilterStatus?.hidden_count ?? 0}</strong>
          </div>
          <div className="detail-stat">
            <span>跳过数量</span>
            <strong>{ingredientFilterStatus?.skipped_count ?? 0}</strong>
          </div>
          <div className="detail-stat">
            <span>错误数量</span>
            <strong>{ingredientFilterStatus?.error_count ?? 0}</strong>
          </div>
        </div>

        <div className="action-row">
          <label className="filter-shell">
            <span>step2 模式</span>
            <select
              value={ingredientFilterProvider}
              onChange={(event) => setIngredientFilterProvider(event.target.value)}
              disabled={loading || working}
            >
              {ingredientFilterProviders.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.id === "deepseek_api" && !deepseekApiKeyConfigured
                    ? `${provider.label} - 未配置 Key`
                    : provider.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="action-button"
            onClick={handleStartIngredientFilterRun}
            disabled={working || loading || ingredientFilterRunning}
          >
            启动 step2 外部AI剔除杂乱项
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={handlePauseIngredientFilterRun}
            disabled={working || !ingredientFilterIsRunning}
          >
            暂停
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={handleResumeIngredientFilterRun}
            disabled={working || ingredientFilterStatus?.status !== "paused"}
          >
            恢复
          </button>
        </div>

        {ingredientFilterStatus?.error_message ? <p>{ingredientFilterStatus.error_message}</p> : null}
      </section>

      {apiKeyModalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <form className="modal-card" onSubmit={handleSaveDeepseekApiKey}>
            <div>
              <p className="eyebrow">DeepSeek API</p>
              <h3>输入 API Key</h3>
              <p className="detail-text-block">
                Key 会保存到本机项目目录的 <code>.env</code> 文件，并同步到当前后端进程。不会提交到 GitHub。
              </p>
            </div>
            <label className="filter-shell modal-field">
              <span>API Key</span>
              <input
                type="password"
                value={apiKeyInput}
                onChange={(event) => setApiKeyInput(event.target.value)}
                autoFocus
                placeholder="sk-..."
              />
            </label>
            <div className="action-row">
              <button type="submit" className="action-button" disabled={apiKeySaving || !apiKeyInput.trim()}>
                保存并启动
              </button>
              <button
                type="button"
                className="action-button secondary"
                disabled={apiKeySaving}
                onClick={() => {
                  setApiKeyModalOpen(false);
                  setApiKeyInput("");
                  setMessage("已取消 DeepSeek API Key 设置。");
                }}
              >
                取消
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}
