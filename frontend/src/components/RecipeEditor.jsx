import { useEffect, useMemo, useState } from "react";

import {
  createRecipeEditorRow,
  fetchRecipeEditorRows,
  fetchRecipeEditorSchema,
  updateRecipeEditorRow
} from "../lib/api";

const DEFAULT_FILTER = {
  id: "filter-1",
  logic: "and",
  field: "ingredient_names",
  operator: "contains",
  value: ""
};

const RECORD_KIND_LABELS = {
  recipe: "正式菜谱",
  backlog: "待办条目"
};

function normalizeText(value) {
  return String(value ?? "").trim().toLowerCase();
}

function matchesCondition(row, condition) {
  const fieldValue = condition.field === "__keyword__" ? Object.values(row).join(" ") : row[condition.field];
  const rowText = normalizeText(fieldValue);
  const filterText = normalizeText(condition.value);

  if (condition.operator === "empty") {
    return !rowText;
  }
  if (condition.operator === "not_empty") {
    return Boolean(rowText);
  }
  if (!filterText) {
    return true;
  }
  if (condition.operator === "equals") {
    return rowText === filterText;
  }
  if (condition.operator === "not_contains") {
    return !rowText.includes(filterText);
  }
  return rowText.includes(filterText);
}

function filterRows(rows, filters, keyword) {
  const activeFilters = filters.filter((filter) => {
    if (filter.operator === "empty" || filter.operator === "not_empty") {
      return filter.field;
    }
    return filter.field && String(filter.value ?? "").trim();
  });
  const normalizedKeyword = normalizeText(keyword);

  return rows.filter((row) => {
    if (normalizedKeyword && !normalizeText(Object.values(row).join(" ")).includes(normalizedKeyword)) {
      return false;
    }
    if (activeFilters.length === 0) {
      return true;
    }
    return activeFilters.reduce((current, condition, index) => {
      const matched = matchesCondition(row, condition);
      if (index === 0) {
        return matched;
      }
      return condition.logic === "or" ? current || matched : current && matched;
    }, true);
  });
}

function buildDefaultFilters(schema) {
  const defaultFields = schema?.default_filters?.length
    ? schema.default_filters
    : ["ingredient_names", "cuisine", "sub_cuisine", "record_kind", "library_section"];

  return defaultFields.map((field, index) => ({
    id: `filter-${index + 1}`,
    logic: index === 0 ? "and" : "and",
    field,
    operator: "contains",
    value: ""
  }));
}

function valueForInput(value, field) {
  if (field.type === "boolean") {
    return Boolean(value);
  }
  if (field.key === "record_kind") {
    return RECORD_KIND_LABELS[value] ?? value ?? "";
  }
  return value ?? "";
}

function displayCellValue(row, field) {
  const value = valueForInput(row[field.key], field);
  if (field.type === "boolean") {
    return value ? "是" : "";
  }
  return String(value ?? "");
}

function EditorFormModal({ mode, fields, options, values, saving, onChange, onClose, onSubmit }) {
  const editableFields = fields.filter((field) => field.editable);

  return (
    <div className="editor-modal-backdrop" role="presentation">
      <section className="editor-modal" role="dialog" aria-modal="true" aria-label={mode === "create" ? "新建条目" : "修改条目"}>
        <header className="editor-modal-header">
          <h2>{mode === "create" ? "新建条目" : "修改条目"}</h2>
          <button type="button" className="icon-action-button" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>

        <div className="editor-modal-body">
          {editableFields.map((field) => (
            <label key={field.key} className={field.type === "longtext" ? "editor-form-field wide" : "editor-form-field"}>
              <span>{field.label}</span>
              <EditorFormControl
                field={field}
                options={options?.[field.key] || []}
                value={values[field.key]}
                onChange={(value) => onChange(field.key, value)}
              />
            </label>
          ))}
        </div>

        <footer className="editor-modal-footer">
          <button type="button" className="editor-tool-button" onClick={onClose}>
            取消
          </button>
          <button type="button" className="editor-tool-button primary" onClick={onSubmit} disabled={saving}>
            {saving ? "保存中" : "保存"}
          </button>
        </footer>
      </section>
    </div>
  );
}

function EditorFormControl({ field, options, value, onChange }) {
  if (field.type === "boolean") {
    return (
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={field.label}
      />
    );
  }

  if (field.key === "record_kind") {
    return (
      <select value={value || "recipe"} onChange={(event) => onChange(event.target.value)}>
        <option value="recipe">正式菜谱</option>
        <option value="backlog">待办条目</option>
      </select>
    );
  }

  if (field.type === "longtext") {
    return (
      <textarea
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        aria-label={field.label}
        rows={5}
      />
    );
  }

  return (
    <>
      <input
        type={field.type === "number" ? "number" : "text"}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        aria-label={field.label}
        list={`modal-options-${field.key}`}
      />
      <datalist id={`modal-options-${field.key}`}>
        {options.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
    </>
  );
}

export default function RecipeEditor() {
  const [schema, setSchema] = useState({ fields: [], options: {}, default_filters: [] });
  const [rows, setRows] = useState([]);
  const [filters, setFilters] = useState([DEFAULT_FILTER]);
  const [keyword, setKeyword] = useState("");
  const [newFilterField, setNewFilterField] = useState("");
  const [modalMode, setModalMode] = useState(null);
  const [modalRecipeId, setModalRecipeId] = useState(null);
  const [modalValues, setModalValues] = useState({});
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(100);
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadEditor() {
      setLoading(true);
      setError("");
      try {
        const [schemaData, rowData] = await Promise.all([
          fetchRecipeEditorSchema(),
          fetchRecipeEditorRows()
        ]);
        if (!active) {
          return;
        }
        setSchema(schemaData);
        setFilters(buildDefaultFilters(schemaData));
        setRows(rowData.items);
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

    loadEditor();
    return () => {
      active = false;
    };
  }, []);

  const fieldOptions = useMemo(
    () => [{ key: "__keyword__", label: "任意字段关键词" }, ...schema.fields],
    [schema.fields]
  );
  const visibleRows = useMemo(() => filterRows(rows, filters, keyword), [rows, filters, keyword]);
  const pageCount = Math.max(1, Math.ceil(visibleRows.length / pageSize));
  const safePageIndex = Math.min(pageIndex, pageCount - 1);
  const pageRows = visibleRows.slice(safePageIndex * pageSize, safePageIndex * pageSize + pageSize);

  useEffect(() => {
    setPageIndex(0);
  }, [filters, keyword, pageSize]);

  function updateFilter(filterId, patch) {
    setFilters((current) => current.map((filter) => (filter.id === filterId ? { ...filter, ...patch } : filter)));
  }

  function addFilter() {
    const field = newFilterField || schema.fields.find((item) => item.editable)?.key || "name";
    setFilters((current) => [
      ...current,
      {
        id: `filter-${Date.now()}`,
        logic: "and",
        field,
        operator: "contains",
        value: ""
      }
    ]);
    setNewFilterField("");
  }

  function openCreateModal() {
    setModalMode("create");
    setModalRecipeId(null);
    setModalValues({ name: "", record_kind: "recipe" });
  }

  function openEditModal(row) {
    const editableValues = {};
    for (const field of schema.fields) {
      if (field.editable) {
        editableValues[field.key] = row[field.key] ?? (field.type === "boolean" ? false : "");
      }
    }
    setModalMode("edit");
    setModalRecipeId(row.id);
    setModalValues(editableValues);
  }

  function closeModal() {
    if (savingId) {
      return;
    }
    setModalMode(null);
    setModalRecipeId(null);
    setModalValues({});
  }

  async function saveModal() {
    const isCreate = modalMode === "create";
    const targetId = isCreate ? "new" : modalRecipeId;
    setSavingId(targetId);
    setError("");
    setMessage("");
    try {
      if (isCreate) {
        const created = await createRecipeEditorRow(modalValues);
        setRows((current) => [created, ...current]);
        setMessage(`已新建：${created.name}`);
      } else {
        const updated = await updateRecipeEditorRow(modalRecipeId, modalValues);
        setRows((current) => current.map((item) => (item.id === modalRecipeId ? updated : item)));
        setMessage(`已保存：${updated.name}`);
      }
      closeModal();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingId(null);
    }
  }

  return (
    <main className="editor-page">
      <section className="panel editor-panel">
        <div className="editor-menu-strip">
          <span>文件</span>
          <span>编辑</span>
          <span>筛选</span>
          <span>数据</span>
          <span>刷新</span>
          <span className="editor-row-count">
            {loading ? "加载中..." : `${visibleRows.length} / ${rows.length} 条，当前第 ${safePageIndex + 1} / ${pageCount} 页`}
          </span>
        </div>
        <div className="editor-toolbar">
          <label className="editor-toolbar-field" htmlFor="editor-keyword">
            <span>搜索</span>
            <input
              id="editor-keyword"
              type="search"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索任意字段"
            />
          </label>

          <select className="editor-toolbar-select" value={newFilterField} onChange={(event) => setNewFilterField(event.target.value)}>
            <option value="">添加筛选字段</option>
            {fieldOptions.map((field) => (
              <option key={field.key} value={field.key}>
                {field.label}
              </option>
            ))}
          </select>
          <button type="button" className="editor-tool-button" onClick={addFilter}>
            添加筛选
          </button>
          <button
            type="button"
            className="editor-tool-button"
            onClick={() => {
              setFilters(buildDefaultFilters(schema));
              setKeyword("");
            }}
          >
            重置
          </button>

          <div className="editor-pager">
            <button
              type="button"
              className="editor-tool-button"
              onClick={() => setPageIndex((current) => Math.max(0, current - 1))}
              disabled={safePageIndex <= 0}
            >
              上一页
            </button>
            <button
              type="button"
              className="editor-tool-button"
              onClick={() => setPageIndex((current) => Math.min(pageCount - 1, current + 1))}
              disabled={safePageIndex >= pageCount - 1}
            >
              下一页
            </button>
            <select
              className="editor-toolbar-select compact"
              value={String(pageSize)}
              onChange={(event) => setPageSize(Number(event.target.value))}
              aria-label="每页行数"
            >
              {[50, 100, 200, 500].map((value) => (
                <option key={value} value={value}>
                  {value} 行
                </option>
              ))}
            </select>
          </div>

          <button type="button" className="editor-tool-button primary" onClick={openCreateModal}>
            新建条目
          </button>
        </div>

        <div className="editor-filter-list">
          {filters.map((filter, index) => {
            const field = schema.fields.find((item) => item.key === filter.field);
            const options = schema.options?.[filter.field] || [];
            return (
              <div key={filter.id} className="editor-filter-row">
                <select
                  value={filter.logic}
                  onChange={(event) => updateFilter(filter.id, { logic: event.target.value })}
                  disabled={index === 0}
                  aria-label="筛选逻辑"
                >
                  <option value="and">和</option>
                  <option value="or">或</option>
                </select>
                <select
                  value={filter.field}
                  onChange={(event) => updateFilter(filter.id, { field: event.target.value, value: "" })}
                  aria-label="筛选字段"
                >
                  {fieldOptions.map((item) => (
                    <option key={item.key} value={item.key}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <select
                  value={filter.operator}
                  onChange={(event) => updateFilter(filter.id, { operator: event.target.value })}
                  aria-label="筛选方式"
                >
                  <option value="contains">包含</option>
                  <option value="equals">等于</option>
                  <option value="not_contains">不包含</option>
                  <option value="empty">为空</option>
                  <option value="not_empty">非空</option>
                </select>
                <input
                  list={`editor-options-${filter.id}`}
                  value={filter.value}
                  onChange={(event) => updateFilter(filter.id, { value: event.target.value })}
                  placeholder={filter.operator === "empty" || filter.operator === "not_empty" ? "" : field?.label ?? "关键词"}
                  disabled={filter.operator === "empty" || filter.operator === "not_empty"}
                />
                <datalist id={`editor-options-${filter.id}`}>
                  {options.map((option) => (
                    <option key={option} value={option} />
                  ))}
                </datalist>
                <button
                  type="button"
                  className="icon-action-button"
                  onClick={() => setFilters((current) => current.filter((item) => item.id !== filter.id))}
                  title="移除筛选条件"
                  aria-label="移除筛选条件"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>

        {error ? <div className="error-banner editor-inline-banner">{error}</div> : null}
        {message ? <div className="editor-success-banner editor-inline-banner">{message}</div> : null}

        <div className="table-shell editor-table-shell">
          <table className="preview-table editor-table">
            <thead>
              <tr>
                <th className="editor-action-column">操作</th>
                {schema.fields.map((field) => (
                  <th key={field.key}>{field.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => {
                return (
                  <tr key={row.id}>
                    <td className="editor-action-column">
                      <button
                        type="button"
                        className="action-button compact"
                        onClick={() => openEditModal(row)}
                      >
                        修改
                      </button>
                    </td>
                    {schema.fields.map((field) => (
                      <td key={`${row.id}-${field.key}`}>
                        <span className="editor-readonly-cell">{displayCellValue(row, field)}</span>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {!loading && visibleRows.length === 0 ? (
          <div className="empty-state compact-empty-state editor-empty-state">
            <p>当前筛选下没有匹配条目。</p>
          </div>
        ) : null}

        {modalMode ? (
          <EditorFormModal
            mode={modalMode}
            fields={schema.fields}
            options={schema.options}
            values={modalValues}
            saving={Boolean(savingId)}
            onChange={(key, value) => setModalValues((current) => ({ ...current, [key]: value }))}
            onClose={closeModal}
            onSubmit={saveModal}
          />
        ) : null}
      </section>
    </main>
  );
}
