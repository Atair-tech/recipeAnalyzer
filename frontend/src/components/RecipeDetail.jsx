import { useState } from "react";

function formatSectionLabel(value) {
  if (!value) {
    return "";
  }

  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean)
    .join(" / ");
}

function TextSection({ title, text, emptyText = "暂无内容" }) {
  return (
    <section className="detail-section">
      <h3>{title}</h3>
      <p>{text || emptyText}</p>
    </section>
  );
}

function DetailStat({ label, value }) {
  return (
    <div className="detail-stat">
      <span>{label}</span>
      <strong>{value || "未填写"}</strong>
    </div>
  );
}

function RecordTypeBanner({ recipe }) {
  if (recipe.record_kind === "backlog") {
    return <div className="warning-banner">这是一条待办事项，来源于“再挑战及待记录”工作表。</div>;
  }

  return null;
}

export default function RecipeDetail({ recipe, loading }) {
  const [showOriginalText, setShowOriginalText] = useState(false);

  if (loading) {
    return (
      <section className="panel detail-panel">
        <div className="empty-state">
          <h3>加载中...</h3>
        </div>
      </section>
    );
  }

  if (!recipe) {
    return (
      <section className="panel detail-panel">
        <div className="empty-state">
          <h3>未选择条目</h3>
          <p>从左侧列表选择一条记录查看完整内容。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel detail-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Record detail</p>
          <h2>{recipe.name}</h2>
        </div>
        <div className="tag-row compact-tag-row">
          <span className="tag">{recipe.record_kind === "backlog" ? recipe.backlog_status : "正式菜谱"}</span>
          {recipe.bmd_flag ? <span className="tag">BMD</span> : null}
          {recipe.cc_flag ? <span className="tag">CC</span> : null}
        </div>
      </div>

      <RecordTypeBanner recipe={recipe} />

      <div className="detail-grid detail-grid-wide">
        <DetailStat label="专题库" value={recipe.library_section} />
        <DetailStat label="分组" value={formatSectionLabel(recipe.section_name)} />
        <DetailStat label="菜系" value={recipe.cuisine} />
        <DetailStat label="亚菜系" value={recipe.sub_cuisine} />
        <DetailStat label="最后记录日期" value={recipe.last_reviewed_on} />
        <DetailStat label="来源/修订备注" value={recipe.source_reference} />
      </div>

      {recipe.alias ? (
        <section className="detail-section">
          <h3>别名/配对名称</h3>
          <p>{recipe.alias}</p>
        </section>
      ) : null}

      <section className="detail-section">
        <h3>自动标签</h3>
        {recipe.managed_tags?.length ? (
          <div className="tag-row">
            {recipe.managed_tags.map((item) => (
              <span key={`${item.name}-${item.source || ""}`} className="tag tag-with-tooltip">
                {item.name}
                <span className="tag-tooltip">
                  <strong>{item.confidence ? `${Math.round(item.confidence * 100)}%` : "AI"}</strong>
                  <span>{item.reason || "无附加说明"}</span>
                </span>
              </span>
            ))}
          </div>
        ) : (
          <p>当前还没有自动标签。</p>
        )}
      </section>

      {recipe.record_kind === "recipe" ? (
        <>
          <TextSection title="食材" text={recipe.ingredients_text} emptyText="未记录食材。" />
          <TextSection title="调料" text={recipe.seasonings_text} emptyText="未单独记录调料。" />

          <section className="detail-section">
            <h3>结构化食材</h3>
            {recipe.ingredients.length === 0 ? <p>当前没有可用于筛选的结构化食材。</p> : null}
            {recipe.ingredients.length > 0 ? (
              <ul className="ingredient-list">
                {recipe.ingredients.map((ingredient) => (
                  <li key={`${ingredient.name}-${ingredient.amount ?? ""}-${ingredient.unit ?? ""}-${ingredient.remark ?? ""}`}>
                    <strong>{ingredient.name}</strong>
                    <span>{[ingredient.amount, ingredient.unit, ingredient.remark].filter(Boolean).join(" ") || "未指定用量"}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <TextSection title="做法及要点" text={recipe.steps_text} emptyText="未录入做法。" />
        </>
      ) : null}

      <TextSection title="系统备注" text={recipe.notes_text} emptyText="无备注。" />

      <section className="detail-section">
        <button
          type="button"
          className="action-button secondary"
          onClick={() => setShowOriginalText((current) => !current)}
        >
          {showOriginalText ? "收起原始 Excel 文本" : "展开原始 Excel 文本"}
        </button>
        {showOriginalText ? (
          <pre className="raw-text-block">{recipe.original_source_text || "当前没有可回放的原始 Excel 内容。"}</pre>
        ) : null}
      </section>
    </section>
  );
}
