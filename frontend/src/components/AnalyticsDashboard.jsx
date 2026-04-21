import { useEffect, useState } from "react";

import { fetchAnalyticsSummary } from "../lib/api";

function SummaryCard({ label, value, note }) {
  return (
    <article className="overview-card">
      <span>{label}</span>
      <strong>{value ?? 0}</strong>
      <p>{note}</p>
    </article>
  );
}

function MetricBars({ title, items, emptyText }) {
  const maxValue = Math.max(...items.map((item) => item.value), 0);

  return (
    <section className="detail-section">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p>{emptyText}</p>
      ) : (
        <div className="metric-bars">
          {items.map((item) => (
            <div key={`${title}-${item.label}`} className="metric-bar-row">
              <div className="metric-bar-meta">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
              <div className="metric-bar-track">
                <div
                  className="metric-bar-fill"
                  style={{ width: `${maxValue === 0 ? 0 : (item.value / maxValue) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
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

  if (loading) {
    return (
      <section className="panel">
        <div className="empty-state compact-empty-state">
          <h3>加载分析中</h3>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel">
        <div className="error-banner">{error}</div>
      </section>
    );
  }

  const summary = analytics?.summary ?? {};
  const chart = analytics?.chart ?? { items: [], dimension_label: "统计维度", scope_label: "全部" };
  const options = analytics?.options ?? { dimensions: [], scopes: [] };

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Analytics</p>
          <h2>数据分析总览</h2>
        </div>
      </div>

      <div className="overview-grid">
        <SummaryCard label="正式菜谱" value={summary.recipe_count} note="当前库里的正式菜谱记录数" />
        <SummaryCard label="待办项" value={summary.backlog_count} note="待挑战和待记录条目数" />
        <SummaryCard label="专题库" value={summary.library_section_count} note="来源于工作簿的顶层专题数" />
        <SummaryCard label="有做法记录" value={summary.record_with_method_count} note="包含做法文本的记录数" />
        <SummaryCard label="结构化食材" value={summary.ingredient_count} note="可用于筛选和统计的食材词典数" />
        <SummaryCard label="同步批次" value={summary.import_batch_count} note="已保留的导入批次数" />
      </div>

      <div className="filter-bar analytics-filter-bar">
        <label className="filter-shell">
          <span>统计维度</span>
          <select value={dimension} onChange={(event) => setDimension(event.target.value)}>
            {options.dimensions.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-shell">
          <span>统计范围</span>
          <select value={scope} onChange={(event) => setScope(event.target.value)}>
            {options.scopes.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-shell">
          <span>显示条数</span>
          <select value={String(topN)} onChange={(event) => setTopN(Number(event.target.value))}>
            {[8, 10, 12, 15, 20, 30].map((value) => (
              <option key={value} value={value}>
                Top {value}
              </option>
            ))}
          </select>
        </label>
      </div>

      <MetricBars
        title={`${chart.dimension_label} / ${chart.scope_label}`}
        items={chart.items}
        emptyText="当前条件下没有可展示的数据。"
      />
    </section>
  );
}
