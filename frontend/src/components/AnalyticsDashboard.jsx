import { useEffect, useMemo, useState } from "react";

import { fetchAnalyticsSummary } from "../lib/api";

function formatPercent(value) {
  if (!Number.isFinite(value)) {
    return "0%";
  }
  return `${Math.round(value)}%`;
}

function SummaryCard({ label, value, note, tone = "default" }) {
  return (
    <article className={`analytics-kpi-card analytics-kpi-card-${tone}`}>
      <span>{label}</span>
      <strong>{value ?? 0}</strong>
      <p>{note}</p>
    </article>
  );
}

function InsightCard({ label, value, note, eyebrow }) {
  return (
    <article className="analytics-insight-card">
      <span className="analytics-insight-eyebrow">{eyebrow}</span>
      <strong>{value}</strong>
      <h3>{label}</h3>
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
        <span className="analytics-section-note">{items.length} 项</span>
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
                  <span>{item.value} 条记录</span>
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
  const chart = analytics?.chart ?? { items: [], dimension_label: "统计维度", scope_label: "全部记录" };
  const options = analytics?.options ?? { dimensions: [], scopes: [] };

  const derived = useMemo(() => {
    const items = chart.items ?? [];
    const totalValue = items.reduce((sum, item) => sum + item.value, 0);
    const topItem = items[0] ?? null;
    const tailItem = items[items.length - 1] ?? null;
    const average = items.length > 0 ? totalValue / items.length : 0;

    return {
      totalValue,
      topItem,
      tailItem,
      average,
      focusRate: totalValue > 0 && topItem ? (topItem.value / totalValue) * 100 : 0
    };
  }, [chart.items]);

  if (loading) {
    return (
      <section className="panel analytics-dashboard-panel">
        <div className="empty-state compact-empty-state">
          <h3>加载数据分析中</h3>
        </div>
      </section>
    );
  }

  if (error) {
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
          <h2>数据分析总览</h2>
          <p>
            当前正在查看 <strong>{chart.dimension_label}</strong> 在 <strong>{chart.scope_label}</strong> 范围下的分布。
          </p>
        </div>
        <div className="analytics-hero-metrics">
          <div className="analytics-hero-pill">
            <span>Top 1 占比</span>
            <strong>{formatPercent(derived.focusRate)}</strong>
          </div>
          <div className="analytics-hero-pill">
            <span>维度项数</span>
            <strong>{chart.items.length}</strong>
          </div>
        </div>
      </div>

      <div className="analytics-kpi-grid">
        <SummaryCard label="正式菜谱" value={summary.recipe_count} note="当前库里的正式菜谱记录数" tone="accent" />
        <SummaryCard label="待办项" value={summary.backlog_count} note="待挑战和待记录条目数" />
        <SummaryCard label="专题库" value={summary.library_section_count} note="来源于工作簿的顶层专题数" />
        <SummaryCard label="有做法记录" value={summary.record_with_method_count} note="包含做法文本的记录数" />
        <SummaryCard label="结构化食材" value={summary.ingredient_count} note="可用于筛选和统计的食材词典数" />
        <SummaryCard label="同步批次" value={summary.import_batch_count} note="已保留的导入批次数" />
      </div>

      <section className="analytics-control-panel">
        <div className="analytics-control-header">
          <div>
            <span className="analytics-section-eyebrow">Control Panel</span>
            <h3>分析视角</h3>
          </div>
        </div>

        <div className="filter-bar analytics-filter-bar analytics-filter-bar-dashboard">
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
      </section>

      <div className="analytics-dashboard-grid">
        <MetricBars
          title={`${chart.dimension_label} / ${chart.scope_label}`}
          items={chart.items}
          emptyText="当前条件下没有可展示的数据。"
        />

        <aside className="analytics-insight-stack">
          <InsightCard
            eyebrow="Leading Segment"
            label={derived.topItem?.label ?? "暂无数据"}
            value={derived.topItem?.value ?? 0}
            note={derived.topItem ? `当前排名第一，约占已展示分布的 ${formatPercent(derived.focusRate)}。` : "当前筛选下没有命中的维度项。"}
          />
          <InsightCard
            eyebrow="Average"
            label="平均分布密度"
            value={derived.average ? derived.average.toFixed(1) : "0.0"}
            note="已展示项目的平均记录数，可用于判断分布是否集中。"
          />
          <InsightCard
            eyebrow="Tail Segment"
            label={derived.tailItem?.label ?? "暂无数据"}
            value={derived.tailItem?.value ?? 0}
            note={derived.tailItem ? "当前已展示列表中的尾部项。适合排查长尾分布。" : "没有可供比较的尾部项。"}
          />
        </aside>
      </div>
    </section>
  );
}
