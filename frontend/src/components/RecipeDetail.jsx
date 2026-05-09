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
      <div className="detail-text-block">{text || emptyText}</div>
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

function SectionTitleWithHint({ title, hint }) {
  return (
    <div className="detail-section-title">
      <h3>{title}</h3>
      <span className="info-tooltip-trigger" tabIndex={0} aria-label={hint}>
        !
        <span className="info-tooltip">{hint}</span>
      </span>
    </div>
  );
}

function RecordTypeBanner({ recipe }) {
  if (recipe.record_kind === "backlog") {
    return <div className="warning-banner">这是一条待办事项，来源于“再挑战及待记录”工作表。</div>;
  }

  return null;
}

function getOriginalSectionText(recipe, key) {
  const originalSections = recipe.original_sections || {};
  return originalSections[key] || recipe[key] || "";
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

  const originalIngredientsText = getOriginalSectionText(recipe, "ingredients_text");
  const originalSeasoningsText = getOriginalSectionText(recipe, "seasonings_text");
  const originalStepsText = getOriginalSectionText(recipe, "steps_text");

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

      {recipe.record_kind === "recipe" ? (
        <>
          <TextSection title="食材" text={originalIngredientsText} emptyText="未填写" />
          <TextSection title="调料" text={originalSeasoningsText} emptyText="未填写" />
          <TextSection title="做法及要点备忘" text={originalStepsText} emptyText="未填写" />
        </>
      ) : null}

      {recipe.notes_text ? <TextSection title="系统备注" text={recipe.notes_text} /> : null}

      {recipe.record_kind === "recipe" ? (
        <>
          <section className="detail-section detail-section-secondary">
            <SectionTitleWithHint
              title="标准化食材（AI生成，仅供参考）"
              hint="这部分由 AI 从原文中抽取，用于筛选、统计和辅助推荐；如与上方原始 Excel 内容不一致，以上方原文为准。"
            />
            {recipe.ingredients.length === 0 ? <div className="detail-text-block">当前没有可用于筛选的结构化食材。</div> : null}
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

          <section className="detail-section detail-section-secondary">
            <SectionTitleWithHint
              title="自动标签（AI生成，仅供参考）"
              hint="标签用于快速浏览和推荐排序，不代表人工确认结论，可在“标签管理”中审查和移除。"
            />
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
              <div className="detail-text-block">当前还没有自动标签。</div>
            )}
          </section>
        </>
      ) : null}

      <section className="detail-section">
        <button
          type="button"
          className="action-button secondary"
          onClick={() => setShowOriginalText((current) => !current)}
        >
          {showOriginalText ? "收起原始 Excel 记录" : "展开原始 Excel 记录"}
        </button>
        {showOriginalText ? (
          <pre className="raw-text-block">{recipe.original_source_text || "当前没有可回放的原始 Excel 内容。"}</pre>
        ) : null}
      </section>
    </section>
  );
}
