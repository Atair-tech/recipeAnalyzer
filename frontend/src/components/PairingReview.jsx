import { useEffect, useMemo, useState } from "react";

import {
  createPairOverride,
  createPairOverridesBulk,
  deletePairOverride,
  fetchPairingReview
} from "../lib/api";

const AUTO_ACCEPT_THRESHOLD = 0.9;

function SuggestionButton({ disabled, label, onClick }) {
  return (
    <button type="button" className="tag pairing-suggestion" disabled={disabled} onClick={onClick}>
      {label}
    </button>
  );
}

function buildPairPayload({ librarySection, mode, item, suggestion }) {
  return mode === "index"
    ? {
        library_section: librarySection,
        index_ref: item.item_ref,
        index_name: item.name,
        detail_ref: suggestion.detail_ref,
        detail_name: suggestion.detail_name
      }
    : {
        library_section: librarySection,
        index_ref: suggestion.index_ref,
        index_name: suggestion.index_name,
        detail_ref: item.item_ref,
        detail_name: item.name
      };
}

function PairingCard({ item, librarySection, mode, busy, onPair }) {
  const suggestions = item.suggestions ?? [];

  return (
    <article className="pairing-item-card">
      <div className="pairing-item-header">
        <div>
          <strong>{item.name}</strong>
          {item.row_number ? <span className="pairing-row-meta">第 {item.row_number} 行</span> : null}
        </div>
        {item.section_name ? <span>{item.section_name}</span> : null}
      </div>
      {suggestions.length > 0 ? (
        <div className="tag-row">
          {suggestions.map((suggestion) => {
            const targetName = mode === "index" ? suggestion.detail_name : suggestion.index_name;

            return (
              <SuggestionButton
                key={`${item.item_ref}-${suggestion.detail_ref || suggestion.index_ref || targetName}`}
                disabled={busy}
                label={`配对 ${targetName} (${Math.round(suggestion.score * 100)}%)`}
                onClick={() => onPair(buildPairPayload({ librarySection, mode, item, suggestion }))}
              />
            );
          })}
        </div>
      ) : (
        <p className="recipe-meta">当前没有足够接近的候选。</p>
      )}
    </article>
  );
}

function ManualPairForm({ section, busy, onPair }) {
  const [indexRef, setIndexRef] = useState("");
  const [detailRef, setDetailRef] = useState("");

  useEffect(() => {
    setIndexRef(section.index_only_items[0]?.item_ref ?? "");
    setDetailRef(section.detail_only_items[0]?.item_ref ?? "");
  }, [section]);

  const selectedIndex = section.index_only_items.find((item) => item.item_ref === indexRef) ?? null;
  const selectedDetail = section.detail_only_items.find((item) => item.item_ref === detailRef) ?? null;
  const canSubmit = Boolean(selectedIndex && selectedDetail && !busy);

  return (
    <section className="detail-section">
      <h4>手动指定配对</h4>
      <div className="manual-pair-grid">
        <label className="filter-shell">
          <span>索引页条目</span>
          <select value={indexRef} onChange={(event) => setIndexRef(event.target.value)}>
            <option value="">请选择</option>
            {section.index_only_items.map((item) => (
              <option key={`manual-index-${item.item_ref}`} value={item.item_ref}>
                {item.name} {item.row_number ? `(第 ${item.row_number} 行)` : ""}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-shell">
          <span>做法页条目</span>
          <select value={detailRef} onChange={(event) => setDetailRef(event.target.value)}>
            <option value="">请选择</option>
            {section.detail_only_items.map((item) => (
              <option key={`manual-detail-${item.item_ref}`} value={item.item_ref}>
                {item.name} {item.row_number ? `(第 ${item.row_number} 行)` : ""}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className="action-button"
          disabled={!canSubmit}
          onClick={() =>
            onPair({
              library_section: section.library_section,
              index_ref: selectedIndex.item_ref,
              index_name: selectedIndex.name,
              detail_ref: selectedDetail.item_ref,
              detail_name: selectedDetail.name
            })
          }
        >
          保存配对
        </button>
      </div>
    </section>
  );
}

function buildAutoAcceptPayloads(sections, threshold) {
  const usedIndexRefs = new Set();
  const usedDetailRefs = new Set();
  const items = [];

  for (const section of sections) {
    for (const item of section.index_only_items) {
      const best = item.suggestions?.[0];
      if (!best || best.score < threshold || !best.detail_ref) {
        continue;
      }

      if (usedIndexRefs.has(item.item_ref) || usedDetailRefs.has(best.detail_ref)) {
        continue;
      }

      usedIndexRefs.add(item.item_ref);
      usedDetailRefs.add(best.detail_ref);
      items.push({
        library_section: section.library_section,
        index_ref: item.item_ref,
        index_name: item.name,
        detail_ref: best.detail_ref,
        detail_name: best.detail_name
      });
    }
  }

  return items;
}

function filterReviewSections(sections, search, selectedSection, suggestionsOnly) {
  const searchText = search.trim().toLowerCase();

  return sections
    .filter((section) => !selectedSection || section.library_section === selectedSection)
    .map((section) => {
      const filterItems = (items) =>
        items.filter((item) => {
          if (suggestionsOnly && (!item.suggestions || item.suggestions.length === 0)) {
            return false;
          }
          if (!searchText) {
            return true;
          }

          const haystacks = [
            section.library_section,
            item.name,
            item.section_name,
            ...(item.suggestions ?? []).map((suggestion) => suggestion.detail_name || suggestion.index_name || "")
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

          return haystacks.includes(searchText);
        });

      const indexOnlyItems = filterItems(section.index_only_items);
      const detailOnlyItems = filterItems(section.detail_only_items);

      return {
        ...section,
        index_only_items: indexOnlyItems,
        detail_only_items: detailOnlyItems,
        index_only_count: indexOnlyItems.length,
        detail_only_count: detailOnlyItems.length
      };
    })
    .filter((section) => section.index_only_count > 0 || section.detail_only_count > 0);
}

export default function PairingReview({ reloadToken }) {
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [workingKey, setWorkingKey] = useState("");
  const [search, setSearch] = useState("");
  const [selectedSection, setSelectedSection] = useState("");
  const [suggestionsOnly, setSuggestionsOnly] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadReview() {
      setLoading(true);
      setError("");

      try {
        const result = await fetchPairingReview();
        if (active) {
          setReview(result);
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

    loadReview();

    return () => {
      active = false;
    };
  }, [reloadToken]);

  async function refreshReview() {
    const result = await fetchPairingReview();
    setReview(result);
  }

  async function handlePair(payload) {
    const requestKey = `${payload.library_section}:${payload.index_ref || payload.index_name}:${payload.detail_ref || payload.detail_name}`;
    setWorkingKey(requestKey);
    setError("");
    setMessage("");

    try {
      await createPairOverride(payload);
      await refreshReview();
      setMessage(`已保存配对规则：${payload.index_name} -> ${payload.detail_name}`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorkingKey("");
    }
  }

  async function handleDelete(overrideId) {
    setWorkingKey(`delete:${overrideId}`);
    setError("");
    setMessage("");

    try {
      await deletePairOverride(overrideId);
      await refreshReview();
      setMessage("已删除配对规则。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorkingKey("");
    }
  }

  const sectionOptions = useMemo(
    () => (review?.sections ?? []).map((section) => section.library_section),
    [review]
  );

  const filteredSections = useMemo(
    () => filterReviewSections(review?.sections ?? [], search, selectedSection, suggestionsOnly),
    [review, search, selectedSection, suggestionsOnly]
  );

  const autoAcceptItems = useMemo(
    () => buildAutoAcceptPayloads(filteredSections, AUTO_ACCEPT_THRESHOLD),
    [filteredSections]
  );

  async function handleAutoAccept() {
    if (autoAcceptItems.length === 0) {
      return;
    }

    setWorkingKey("bulk-auto-accept");
    setError("");
    setMessage("");

    try {
      const result = await createPairOverridesBulk(autoAcceptItems);
      await refreshReview();
      setMessage(`已批量保存 ${result.count} 条高置信配对规则。`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setWorkingKey("");
    }
  }

  const summary = review?.summary ?? {};

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Pairing review</p>
          <h2>未完全配对条目审查</h2>
        </div>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}
      {message ? <div className="success-banner">{message}</div> : null}

      {loading ? (
        <div className="empty-state compact-empty-state">
          <h3>正在分析工作簿</h3>
          <p>系统正在重新比对索引页和做法页。</p>
        </div>
      ) : null}

      {!loading && review ? (
        <div className="section-stack">
          <div className="import-summary-grid import-summary-grid-wide">
            <div className="detail-stat">
              <span>源文件</span>
              <strong>{review.source_file_name}</strong>
            </div>
            <div className="detail-stat">
              <span>已配对</span>
              <strong>{summary.paired_recipes ?? 0}</strong>
            </div>
            <div className="detail-stat">
              <span>仅索引页</span>
              <strong>{summary.index_only_recipes ?? 0}</strong>
            </div>
            <div className="detail-stat">
              <span>仅做法页</span>
              <strong>{summary.detail_only_recipes ?? 0}</strong>
            </div>
            <div className="detail-stat">
              <span>配对规则</span>
              <strong>{summary.pair_override_count ?? 0}</strong>
            </div>
            <div className="detail-stat">
              <span>专题库</span>
              <strong>{(summary.library_sections ?? []).length}</strong>
            </div>
          </div>

          <label className="search-shell" htmlFor="pairing-search">
            <span>搜索未配对项</span>
            <input
              id="pairing-search"
              type="search"
              value={search}
              placeholder="按专题名、条目名或建议候选过滤"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          <div className="filter-bar pairing-filter-bar">
            <label className="filter-shell" htmlFor="pairing-section-filter">
              <span>专题库</span>
              <select
                id="pairing-section-filter"
                value={selectedSection}
                onChange={(event) => setSelectedSection(event.target.value)}
              >
                <option value="">全部</option>
                {sectionOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

            <label className="toggle-shell">
              <input
                type="checkbox"
                checked={suggestionsOnly}
                onChange={(event) => setSuggestionsOnly(event.target.checked)}
              />
              <span>只看有建议的条目</span>
            </label>

            <button
              type="button"
              className="action-button secondary"
              disabled={workingKey !== "" || autoAcceptItems.length === 0}
              onClick={handleAutoAccept}
            >
              一键接受高置信建议 ({autoAcceptItems.length})
            </button>

            <button
              type="button"
              className="action-button secondary filter-reset"
              onClick={() => {
                setSearch("");
                setSelectedSection("");
                setSuggestionsOnly(false);
              }}
            >
              清空筛选
            </button>
          </div>

          <section className="detail-section">
            <h3>当前规则</h3>
            {review.overrides.length === 0 ? (
              <p>还没有人工配对规则。保存后，后续预览和导入都会复用这些规则。</p>
            ) : (
              <div className="pairing-override-list">
                {review.overrides.map((item) => (
                  <article
                    key={`override-${item.id}-${item.index_ref || item.index_name}-${item.detail_ref || item.detail_name}`}
                    className="history-card pairing-override-card"
                  >
                    <div className="history-card-header">
                      <strong>{item.library_section}</strong>
                      <span>{item.created_at}</span>
                    </div>
                    <h3>{`${item.index_name} -> ${item.detail_name}`}</h3>
                    <div className="action-row">
                      <button
                        type="button"
                        className="action-button secondary"
                        onClick={() => handleDelete(item.id)}
                        disabled={workingKey === `delete:${item.id}`}
                      >
                        删除规则
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="detail-section">
            <h3>待审查专题</h3>
            {filteredSections.length === 0 ? (
              <p>当前筛选条件下没有待处理的未配对条目。</p>
            ) : (
              <div className="pairing-section-list">
                {filteredSections.map((section) => (
                  <article key={`section-${section.library_section}`} className="pairing-section-card">
                    <div className="panel-header pairing-section-header">
                      <div>
                        <p className="eyebrow">Section</p>
                        <h3>{section.library_section}</h3>
                      </div>
                      <div className="tag-row compact-tag-row">
                        <span className="tag">仅索引页 {section.index_only_count}</span>
                        <span className="tag muted">仅做法页 {section.detail_only_count}</span>
                      </div>
                    </div>

                    {section.index_only_items.length > 0 && section.detail_only_items.length > 0 ? (
                      <ManualPairForm section={section} busy={workingKey !== ""} onPair={handlePair} />
                    ) : null}

                    <div className="pairing-grid">
                      <section className="pairing-column">
                        <h4>仅索引页</h4>
                        {section.index_only_items.length === 0 ? (
                          <p className="recipe-meta">没有仅索引页条目。</p>
                        ) : (
                          <div className="pairing-item-list">
                            {section.index_only_items.map((item) => (
                              <PairingCard
                                key={`index-${item.item_ref}`}
                                item={item}
                                librarySection={section.library_section}
                                mode="index"
                                busy={workingKey !== ""}
                                onPair={handlePair}
                              />
                            ))}
                          </div>
                        )}
                      </section>

                      <section className="pairing-column">
                        <h4>仅做法页</h4>
                        {section.detail_only_items.length === 0 ? (
                          <p className="recipe-meta">没有仅做法页条目。</p>
                        ) : (
                          <div className="pairing-item-list">
                            {section.detail_only_items.map((item) => (
                              <PairingCard
                                key={`detail-${item.item_ref}`}
                                item={item}
                                librarySection={section.library_section}
                                mode="detail"
                                busy={workingKey !== ""}
                                onPair={handlePair}
                              />
                            ))}
                          </div>
                        )}
                      </section>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      ) : null}
    </section>
  );
}
