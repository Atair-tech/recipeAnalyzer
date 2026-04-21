import { useState } from "react";

import { exportRecipes } from "../lib/api";

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

function RecordBadge({ recipe }) {
  if (recipe.record_kind === "backlog") {
    return <span className="tag muted">{recipe.backlog_status}</span>;
  }
  return <span className="tag">正式菜谱</span>;
}

function toggleManagedTag(selectedTags, targetTag) {
  if (selectedTags.includes(targetTag)) {
    return selectedTags.filter((item) => item !== targetTag);
  }
  return [...selectedTags, targetTag];
}

export default function RecipeList({
  recipes,
  search,
  status,
  librarySection,
  sectionName,
  cuisine,
  ingredient,
  managedTags,
  bmdOnly,
  ccOnly,
  filterOptions,
  onSearchChange,
  onStatusChange,
  onLibrarySectionChange,
  onSectionNameChange,
  onCuisineChange,
  onIngredientChange,
  onManagedTagsChange,
  onBmdOnlyChange,
  onCcOnlyChange,
  onResetFilters,
  onSelectRecipe,
  selectedRecipeId,
  loading
}) {
  const [showManagedTagDropdown, setShowManagedTagDropdown] = useState(false);
  const [showFilters, setShowFilters] = useState(true);

  return (
    <section className="panel list-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Recipe library</p>
          <h2>菜谱库</h2>
        </div>
        <div className="results-chip">{loading ? "加载中..." : `${recipes.length} 条`}</div>
      </div>

      <label className="search-shell" htmlFor="recipe-search">
        <span>关键词搜索</span>
        <input
          id="recipe-search"
          name="recipe-search"
          type="search"
          placeholder="搜索菜名、专题库、分组、做法或备注"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>

      <section className="filter-card">
        <div className="filter-card-header">
          <div className="filter-inline-label">筛选</div>

          <div className="filter-card-actions">
            <button
              type="button"
              className="action-button secondary"
              onClick={() =>
                exportRecipes({
                  search,
                  status,
                  librarySection,
                  sectionName,
                  cuisine,
                  ingredient,
                  managedTags,
                  bmdOnly,
                  ccOnly
                })
              }
            >
              导出结果
            </button>
            <button type="button" className="action-button secondary filter-reset" onClick={onResetFilters}>
              清空筛选
            </button>
            <button
              type="button"
              className="filter-collapse-button"
              onClick={() => setShowFilters((current) => !current)}
              aria-expanded={showFilters}
              aria-label={showFilters ? "收起筛选条件" : "展开筛选条件"}
              title={showFilters ? "收起筛选条件" : "展开筛选条件"}
            >
              <span className={showFilters ? "filter-collapse-arrow expanded" : "filter-collapse-arrow"}>▼</span>
            </button>
          </div>
        </div>

        {showFilters ? (
          <>
            <div className="filter-panel-grid">
              <label className="filter-shell" htmlFor="status-filter">
                <span>类型</span>
                <select id="status-filter" value={status} onChange={(event) => onStatusChange(event.target.value)}>
                  <option value="">全部</option>
                  <option value="recipe">正式菜谱</option>
                  <option value="待挑战">待挑战</option>
                  <option value="待记录">待记录</option>
                </select>
              </label>

              <label className="filter-shell" htmlFor="library-section-filter">
                <span>专题库</span>
                <select
                  id="library-section-filter"
                  value={librarySection}
                  onChange={(event) => onLibrarySectionChange(event.target.value)}
                >
                  <option value="">全部</option>
                  {filterOptions.library_sections.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="filter-shell" htmlFor="section-name-filter">
                <span>分组</span>
                <select id="section-name-filter" value={sectionName} onChange={(event) => onSectionNameChange(event.target.value)}>
                  <option value="">全部</option>
                  {filterOptions.section_names.map((option) => (
                    <option key={option} value={option}>
                      {formatSectionLabel(option)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="filter-shell" htmlFor="cuisine-filter">
                <span>菜系</span>
                <select id="cuisine-filter" value={cuisine} onChange={(event) => onCuisineChange(event.target.value)}>
                  <option value="">全部</option>
                  {filterOptions.cuisines.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>

              <label className="filter-shell" htmlFor="ingredient-filter">
                <span>食材</span>
                <select id="ingredient-filter" value={ingredient} onChange={(event) => onIngredientChange(event.target.value)}>
                  <option value="">全部</option>
                  {filterOptions.ingredients.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <section className="filter-checkbox-card">
              <button
                type="button"
                className="filter-dropdown-trigger"
                onClick={() => setShowManagedTagDropdown((current) => !current)}
                aria-expanded={showManagedTagDropdown}
              >
                <span>自动标签</span>
                <span className="filter-checkbox-summary">
                  {managedTags.length > 0 ? `已选 ${managedTags.length} 项，需全部命中` : "未选择"}
                </span>
                <span className="filter-dropdown-arrow">{showManagedTagDropdown ? "▲" : "▼"}</span>
              </button>

              {showManagedTagDropdown ? (
                <div className="filter-dropdown-panel">
                  <div className="checkbox-grid">
                    {filterOptions.managed_tags.map((option) => (
                      <label key={option} className="checkbox-chip">
                        <input
                          type="checkbox"
                          checked={managedTags.includes(option)}
                          onChange={() => onManagedTagsChange(toggleManagedTag(managedTags, option))}
                        />
                        <span>{option}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>

            <div className="filter-toggle-row">
              <label className="toggle-shell">
                <input type="checkbox" checked={bmdOnly} onChange={(event) => onBmdOnlyChange(event.target.checked)} />
                <span>BMD</span>
              </label>

              <label className="toggle-shell">
                <input type="checkbox" checked={ccOnly} onChange={(event) => onCcOnlyChange(event.target.checked)} />
                <span>CC</span>
              </label>
            </div>
          </>
        ) : null}
      </section>

      <div className="recipe-list">
        {recipes.length === 0 ? (
          <div className="empty-state">
            <h3>没有匹配结果</h3>
            <p>可以调整筛选条件或修改搜索词。</p>
          </div>
        ) : (
          recipes.map((recipe) => (
            <button
              key={recipe.id}
              type="button"
              className={selectedRecipeId === recipe.id ? "recipe-card active" : "recipe-card"}
              onClick={() => onSelectRecipe(recipe.id)}
            >
              <div className="recipe-card-header">
                <h3>{recipe.name}</h3>
                <RecordBadge recipe={recipe} />
              </div>

              <p className="recipe-meta">
                {[recipe.library_section, formatSectionLabel(recipe.section_name), recipe.cuisine].filter(Boolean).join(" / ") || "未归类"}
              </p>

              <div className="tag-row compact-tag-row">
                {recipe.managed_tags?.map((recipeTag) => (
                  <span key={`${recipe.id}-managed-${recipeTag}`} className="tag">
                    {recipeTag}
                  </span>
                ))}
                {recipe.sub_cuisine ? <span className="tag muted">{recipe.sub_cuisine}</span> : null}
                {recipe.bmd_flag ? <span className="tag">BMD</span> : null}
                {recipe.cc_flag ? <span className="tag">CC</span> : null}
                {recipe.last_reviewed_on ? <span className="tag muted">{recipe.last_reviewed_on}</span> : null}
                {!recipe.last_reviewed_on && recipe.source_reference ? (
                  <span className="tag muted">{recipe.source_reference}</span>
                ) : null}
              </div>
            </button>
          ))
        )}
      </div>
    </section>
  );
}
