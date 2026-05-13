import { useEffect, useState } from "react";

import { fetchAnalyticsSummary } from "../lib/api";

function SummaryCard({ label, value, note, tone = "default" }) {
  return (
    <article className={`analytics-kpi-card analytics-kpi-card-${tone}`}>
      <span>{label}</span>
      <strong>{value ?? 0}</strong>
      <p>{note}</p>
    </article>
  );
}

function MetricBars({ title, items, emptyText }) {
  const maxValue = Math.max(...items.map((item) => item.value), 0);

  return (
    <section className="analytics-chart-card">
      <div className="analytics-section-heading">
        <div>
          <span className="analytics-section-eyebrow">Ranking</span>
          <h3>{title}</h3>
        </div>
        <span className="analytics-section-note">{items.length} {"\u9879"}</span>
      </div>

      {items.length === 0 ? (
        <div className="empty-state compact-empty-state">
          <p>{emptyText}</p>
        </div>
      ) : (
        <div className="analytics-rank-list">
          {items.map((item, index) => (
            <div key={`${title}-${item.label}`} className="analytics-rank-item">
              <div className="analytics-rank-main">
                <span className="analytics-rank-index">{String(index + 1).padStart(2, "0")}</span>
                <div className="analytics-rank-copy">
                  <strong>{item.label}</strong>
                  <span>
                    {item.value} {"\u6761\u8bb0\u5f55"}
                  </span>
                </div>
              </div>
              <div className="analytics-rank-bar-shell">
                <div className="analytics-rank-bar-track">
                  <div
                    className="analytics-rank-bar-fill"
                    style={{ width: `${maxValue === 0 ? 0 : (item.value / maxValue) * 100}%` }}
                  />
                </div>
                <span className="analytics-rank-value">{item.value}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function isTauriRuntime() {
  return Boolean(
    typeof window !== "undefined" &&
      (window.__TAURI_INTERNALS__ ||
        window.location.protocol === "tauri:" ||
        window.location.hostname === "tauri.localhost")
  );
}

async function openRecipeEditor() {
  if (isTauriRuntime()) {
    try {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      const existingEditor = await WebviewWindow.getByLabel("recipe-editor");
      if (existingEditor) {
        await existingEditor.show();
        await existingEditor.setFocus();
        return;
      }

      const editorWindow = new WebviewWindow("recipe-editor", {
        url: "/#editor",
        title: "菜谱编辑模式",
        width: 1440,
        height: 920,
        minWidth: 1100,
        minHeight: 760,
        resizable: true,
        focus: true
      });
      editorWindow.once("tauri://error", (event) => {
        window.alert(`无法打开编辑模式窗口：${event.payload || "未知错误"}`);
      });
      return;
    } catch (error) {
      window.alert(`无法打开编辑模式窗口：${error?.message || String(error)}`);
      return;
    }
  }

  const editorUrl = `${window.location.origin}${window.location.pathname}#editor`;
  const opened = window.open(editorUrl, "_blank");
  if (opened) {
    opened.opener = null;
  }
  if (!opened) {
    window.location.hash = "editor";
  }
}

export default function AnalyticsDashboard({ reloadToken }) {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dimension, setDimension] = useState("library_section");
  const [scope, setScope] = useState("all");
  const [topN, setTopN] = useState(12);

  useEffect(() => {
    let active = true;

    async function loadAnalytics() {
      setLoading(true);
      setError("");

      try {
        const analyticsData = await fetchAnalyticsSummary({ dimension, scope, topN });
        if (active) {
          setAnalytics(analyticsData);
        }
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

    loadAnalytics();

    return () => {
      active = false;
    };
  }, [dimension, scope, topN, reloadToken]);

  const summary = analytics?.summary ?? {};
  const chart = analytics?.chart ?? {
    items: [],
    dimension_label: "\u7edf\u8ba1\u7ef4\u5ea6",
    scope_label: "\u5168\u90e8\u8bb0\u5f55"
  };
  const options = analytics?.options ?? { dimensions: [], scopes: [] };

  if (loading && !analytics) {
    return (
      <section className="panel analytics-dashboard-panel">
        <div className="empty-state compact-empty-state">
          <h3>{"\u52a0\u8f7d\u6570\u636e\u5206\u6790\u4e2d..."}</h3>
        </div>
      </section>
    );
  }

  if (error && !analytics) {
    return (
      <section className="panel analytics-dashboard-panel">
        <div className="error-banner">{error}</div>
      </section>
    );
  }

  return (
    <section className="panel analytics-dashboard-panel">
      <div className="analytics-hero">
        <div className="analytics-hero-copy">
          <span className="analytics-hero-eyebrow">Insight Workspace</span>
          <h2>{"\u83dc\u8c31\u5e93\u603b\u89c8"}</h2>
        </div>
        <button type="button" className="action-button analytics-editor-button" onClick={openRecipeEditor}>
          编辑模式
        </button>
      </div>

      <div className="analytics-kpi-grid">
        <SummaryCard
          label={"\u6b63\u5f0f\u83dc\u8c31"}
          value={summary.recipe_count}
          note={"\u5f53\u524d\u5e93\u4e2d\u7684\u6b63\u5f0f\u83dc\u8c31\u8bb0\u5f55\u6570"}
          tone="accent"
        />
        <SummaryCard
          label={"\u5f85\u529e\u9879"}
          value={summary.backlog_count}
          note={"\u5f85\u6311\u6218\u548c\u5f85\u8bb0\u5f55\u6761\u76ee\u6570"}
        />
        <SummaryCard
          label={"\u4e13\u9898\u5e93"}
          value={summary.library_section_count}
          note={"\u6765\u6e90\u4e8e\u5de5\u4f5c\u7c3f\u7684\u9876\u5c42\u4e13\u9898\u6570"}
        />
        <SummaryCard
          label={"\u6709\u505a\u6cd5\u8bb0\u5f55"}
          value={summary.record_with_method_count}
          note={"\u5305\u542b\u505a\u6cd5\u6587\u672c\u7684\u8bb0\u5f55\u6570"}
        />
        <SummaryCard
          label={"\u7ed3\u6784\u5316\u98df\u6750"}
          value={summary.ingredient_count}
          note={"\u53ef\u7528\u4e8e\u7b5b\u9009\u548c\u7edf\u8ba1\u7684\u98df\u6750\u8bcd\u5178\u6570"}
        />
        <SummaryCard
          label={"\u540c\u6b65\u6279\u6b21"}
          value={summary.import_batch_count}
          note={"\u5df2\u4fdd\u7559\u7684\u5bfc\u5165\u6279\u6b21\u6570"}
        />
      </div>

      <section className="analytics-control-panel">
        <div className="analytics-control-header">
          <div>
            <span className="analytics-section-eyebrow">Control Panel</span>
            <h3>{"\u5206\u6790\u89c6\u89d2"}</h3>
          </div>
          {loading ? <span className="inline-status-note analytics-updating-note">正在更新图表...</span> : null}
        </div>

        <div className="filter-bar analytics-filter-bar analytics-filter-bar-dashboard">
          <label className="filter-shell">
            <span>{"\u7edf\u8ba1\u7ef4\u5ea6"}</span>
            <select value={dimension} onChange={(event) => setDimension(event.target.value)}>
              {options.dimensions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="filter-shell">
            <span>{"\u7edf\u8ba1\u8303\u56f4"}</span>
            <select value={scope} onChange={(event) => setScope(event.target.value)}>
              {options.scopes.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="filter-shell">
            <span>{"\u663e\u793a\u6761\u6570"}</span>
            <select value={String(topN)} onChange={(event) => setTopN(Number(event.target.value))}>
              {[8, 10, 12, 15, 20, 30].map((value) => (
                <option key={value} value={value}>
                  Top {value}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="analytics-dashboard-grid">
        <MetricBars
          title={`${chart.dimension_label} / ${chart.scope_label}`}
          items={chart.items}
          emptyText={"\u5f53\u524d\u6761\u4ef6\u4e0b\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u6570\u636e\u3002"}
        />
      </div>
    </section>
  );
}
