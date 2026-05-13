import { useEffect, useMemo, useState } from "react";

import {
  applyRecipeEditorTableChanges,
  createRecipeEditorRow,
  executeRecipeEditorSql,
  fetchRecipeEditorSchema,
  fetchRecipeEditorTableRows,
  fetchRecipeEditorTables,
  updateRecipeEditorRow
} from "../lib/api";

const RECORD_KIND_LABELS = {
  recipe: "正式菜谱",
  backlog: "待办条目"
};

const MIN_COLUMN_WIDTH = 56;
const ROW_NUMBER_COLUMN_WIDTH = 44;
const ACTION_COLUMN_WIDTH = 72;

function initialColumnWidth(columnName, columnType = "") {
  const normalizedType = String(columnType || "").toUpperCase();
  if (columnName === "id" || columnName.endsWith("_id") || columnName === "run_id") {
    return 82;
  }
  if (columnName.endsWith("_flag") || columnName === "is_visible" || columnName === "is_active") {
    return 76;
  }
  if (columnName.includes("hash")) {
    return 240;
  }
  if (columnName.includes("json") || columnName.includes("raw_response") || columnName.includes("source_text")) {
    return 360;
  }
  if (columnName.includes("text") || columnName.includes("message") || columnName.includes("reason") || columnName.includes("error")) {
    return 280;
  }
  if (columnName.endsWith("_at") || columnName.endsWith("_on") || columnName.includes("date") || columnName.includes("time")) {
    return 170;
  }
  if (columnName === "name" || columnName.endsWith("_name") || columnName === "model") {
    return 180;
  }
  if (normalizedType.includes("INTEGER") || normalizedType.includes("REAL")) {
    return 96;
  }
  return 150;
}

function buildInitialColumnWidths(columns) {
  return Object.fromEntries(columns.map((column) => [column.name, initialColumnWidth(column.name, column.type)]));
}

function buildInitialSqlColumnWidths(columns) {
  return Object.fromEntries(columns.map((column) => [column, initialColumnWidth(column)]));
}

function normalizeEditableValue(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function rowPrimaryKey(row, columns) {
  const primaryColumns = columns.filter((column) => column.primary_key).map((column) => column.name);
  if (primaryColumns.length === 0) {
    return null;
  }
  return Object.fromEntries(primaryColumns.map((column) => [column, row[column]]));
}

function rowEditKey(row, columns) {
  const pk = rowPrimaryKey(row, columns);
  return pk ? JSON.stringify(pk) : "";
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

function displayValue(value) {
  if (value === null || value === undefined) {
    return <span className="editor-null-value">NULL</span>;
  }
  if (typeof value === "boolean") {
    return value ? "1" : "0";
  }
  return String(value);
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
  const [recipeSchema, setRecipeSchema] = useState({ fields: [], options: {} });
  const [tableSchema, setTableSchema] = useState({ tables: [], default_table: "" });
  const [selectedTable, setSelectedTable] = useState("");
  const [rows, setRows] = useState([]);
  const [totalRows, setTotalRows] = useState(0);
  const [columnFilters, setColumnFilters] = useState({});
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(100);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [modalMode, setModalMode] = useState(null);
  const [modalRecipeId, setModalRecipeId] = useState(null);
  const [modalValues, setModalValues] = useState({});
  const [activeTab, setActiveTab] = useState("browse");
  const [sqlText, setSqlText] = useState("SELECT * FROM recipes LIMIT 50;");
  const [sqlResult, setSqlResult] = useState(null);
  const [sqlRunning, setSqlRunning] = useState(false);
  const [columnWidths, setColumnWidths] = useState({});
  const [sqlColumnWidths, setSqlColumnWidths] = useState({});
  const [pendingEdits, setPendingEdits] = useState({});
  const [editHistory, setEditHistory] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadInitialData() {
      setLoading(true);
      setError("");
      try {
        const [recipeSchemaData, tableSchemaData] = await Promise.all([
          fetchRecipeEditorSchema(),
          fetchRecipeEditorTables()
        ]);
        if (!active) {
          return;
        }
        setRecipeSchema(recipeSchemaData);
        setTableSchema(tableSchemaData);
        setSelectedTable(tableSchemaData.default_table || tableSchemaData.tables[0]?.name || "");
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

    loadInitialData();
    return () => {
      active = false;
    };
  }, []);

  const selectedTableInfo = useMemo(
    () => tableSchema.tables.find((table) => table.name === selectedTable) || null,
    [selectedTable, tableSchema.tables]
  );
  const columns = selectedTableInfo?.columns || [];
  const modalFields = useMemo(() => {
    const columnNames = new Set(columns.map((column) => column.name));
    return recipeSchema.fields.filter((field) => columnNames.has(field.key));
  }, [columns, recipeSchema.fields]);
  const pageCount = Math.max(1, Math.ceil(totalRows / pageSize));
  const safePageIndex = Math.min(pageIndex, pageCount - 1);
  const isRecipeTable = selectedTable === "recipes";
  const pendingChangeCount = useMemo(
    () => Object.values(pendingEdits).reduce((total, rowEdits) => total + Object.keys(rowEdits.values || {}).length, 0),
    [pendingEdits]
  );
  const canEditSelectedTable = columns.some((column) => column.primary_key);

  useEffect(() => {
    setColumnWidths(buildInitialColumnWidths(columns));
  }, [selectedTable, columns]);

  useEffect(() => {
    if (!selectedTable) {
      return;
    }

    let active = true;
    async function loadRows() {
      setTableLoading(true);
      setError("");
      try {
        const data = await fetchRecipeEditorTableRows({
          table: selectedTable,
          filters: columnFilters,
          limit: pageSize,
          offset: safePageIndex * pageSize
        });
        if (!active) {
          return;
        }
        setRows(data.items);
        setTotalRows(data.total);
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      } finally {
        if (active) {
          setTableLoading(false);
        }
      }
    }

    loadRows();
    return () => {
      active = false;
    };
  }, [selectedTable, columnFilters, pageSize, safePageIndex]);

  useEffect(() => {
    setPageIndex(0);
  }, [columnFilters, pageSize, selectedTable]);

  function updateColumnFilter(columnName, value) {
    setColumnFilters((current) => {
      const next = { ...current };
      if (value.trim()) {
        next[columnName] = value;
      } else {
        delete next[columnName];
      }
      return next;
    });
  }

  function clearFilters() {
    if (pendingChangeCount && !window.confirm("当前有未写入的更改。清空筛选会放弃这些更改，是否继续？")) {
      return;
    }
    setPendingEdits({});
    setEditHistory([]);
    setColumnFilters({});
  }

  function changeTable(tableName) {
    if (pendingChangeCount && !window.confirm("当前有未写入的更改。切换表会放弃这些更改，是否继续？")) {
      return;
    }
    setSelectedTable(tableName);
    setColumnFilters({});
    setRows([]);
    setTotalRows(0);
    setPendingEdits({});
    setEditHistory([]);
    setMessage("");
    setError("");
  }

  function openCreateModal() {
    setModalMode("create");
    setModalRecipeId(null);
    setModalValues({ name: "", record_kind: "recipe" });
  }

  function openEditModal(row) {
    const editableValues = {};
    for (const field of modalFields) {
      if (field.editable) {
        editableValues[field.key] = valueForInput(row[field.key], field) ?? (field.type === "boolean" ? false : "");
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
        setMessage(`已新建：${created.name}`);
      } else {
        const updated = await updateRecipeEditorRow(modalRecipeId, modalValues);
        setMessage(`已保存：${updated.name}`);
      }
      closeModal();
      const data = await fetchRecipeEditorTableRows({
        table: selectedTable,
        filters: columnFilters,
        limit: pageSize,
        offset: safePageIndex * pageSize
      });
      setRows(data.items);
      setTotalRows(data.total);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSavingId(null);
    }
  }

  async function runSql() {
    setSqlRunning(true);
    setError("");
    setMessage("");
    setSqlResult(null);
    try {
      const result = await executeRecipeEditorSql(sqlText);
      setSqlResult(result);
      setSqlColumnWidths(result.kind === "rows" ? buildInitialSqlColumnWidths(result.columns) : {});
      setMessage(result.message || "SQL 执行完成");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSqlRunning(false);
    }
  }

  function startColumnResize(kind, columnName, startWidth, event) {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const setter = kind === "sql" ? setSqlColumnWidths : setColumnWidths;

    function handleMouseMove(moveEvent) {
      const nextWidth = Math.max(MIN_COLUMN_WIDTH, Math.round(startWidth + moveEvent.clientX - startX));
      setter((current) => ({ ...current, [columnName]: nextWidth }));
    }

    function handleMouseUp() {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.classList.remove("column-resize-active");
    }

    document.body.classList.add("column-resize-active");
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  }

  function getDisplayedCellValue(row, columnName) {
    const key = rowEditKey(row, columns);
    if (key && Object.prototype.hasOwnProperty.call(pendingEdits[key]?.values || {}, columnName)) {
      return pendingEdits[key].values[columnName];
    }
    return row[columnName];
  }

  function stageCellEdit(row, column, rawValue) {
    const key = rowEditKey(row, columns);
    const pk = rowPrimaryKey(row, columns);
    if (!key || !pk || column.primary_key) {
      return;
    }

    const columnName = column.name;
    const originalValue = normalizeEditableValue(row[columnName]);
    const value = rawValue;
    const previousPendingValue = pendingEdits[key]?.values?.[columnName];
    const previousValue = previousPendingValue === undefined ? originalValue : previousPendingValue;
    if (value === previousValue) {
      return;
    }

    setEditHistory((current) => [...current, { rowKey: key, columnName, previousValue }]);
    setPendingEdits((current) => {
      const next = { ...current };
      const existing = next[key] || { pk, values: {} };
      const nextValues = { ...existing.values };
      if (value === originalValue) {
        delete nextValues[columnName];
      } else {
        nextValues[columnName] = value;
      }
      if (Object.keys(nextValues).length === 0) {
        delete next[key];
      } else {
        next[key] = { pk, values: nextValues };
      }
      return next;
    });
  }

  function undoLastEdit() {
    setEditHistory((currentHistory) => {
      const lastEdit = currentHistory[currentHistory.length - 1];
      if (!lastEdit) {
        return currentHistory;
      }
      setPendingEdits((current) => {
        const next = { ...current };
        const rowEdit = next[lastEdit.rowKey];
        if (!rowEdit) {
          return current;
        }
        const row = rows.find((item) => rowEditKey(item, columns) === lastEdit.rowKey);
        const originalValue = normalizeEditableValue(row?.[lastEdit.columnName]);
        const nextValues = { ...rowEdit.values };
        if (lastEdit.previousValue === originalValue) {
          delete nextValues[lastEdit.columnName];
        } else {
          nextValues[lastEdit.columnName] = lastEdit.previousValue;
        }
        if (Object.keys(nextValues).length === 0) {
          delete next[lastEdit.rowKey];
        } else {
          next[lastEdit.rowKey] = { ...rowEdit, values: nextValues };
        }
        return next;
      });
      return currentHistory.slice(0, -1);
    });
  }

  function discardPendingChanges() {
    if (!pendingChangeCount) {
      return;
    }
    if (!window.confirm(`确定放弃 ${pendingChangeCount} 个未写入的更改吗？`)) {
      return;
    }
    setPendingEdits({});
    setEditHistory([]);
    setMessage("已放弃未写入的更改");
    setError("");
  }

  async function writePendingChanges() {
    if (!pendingChangeCount) {
      return;
    }
    if (!window.confirm(`确定将 ${pendingChangeCount} 个更改写入数据库吗？`)) {
      return;
    }
    setTableLoading(true);
    setError("");
    setMessage("");
    try {
      const changes = Object.values(pendingEdits);
      const result = await applyRecipeEditorTableChanges({ table: selectedTable, changes });
      const data = await fetchRecipeEditorTableRows({
        table: selectedTable,
        filters: columnFilters,
        limit: pageSize,
        offset: safePageIndex * pageSize
      });
      setRows(data.items);
      setTotalRows(data.total);
      setPendingEdits({});
      setEditHistory([]);
      setMessage(result.message || "更改已写入数据库");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setTableLoading(false);
    }
  }

  return (
    <main className="editor-page">
      <section className="panel editor-panel">
        <div className="editor-menu-strip">
          <button
            type="button"
            className={activeTab === "browse" ? "editor-menu-tab active" : "editor-menu-tab"}
            onClick={() => setActiveTab("browse")}
          >
            浏览数据
          </button>
          <button
            type="button"
            className={activeTab === "sql" ? "editor-menu-tab active" : "editor-menu-tab"}
            onClick={() => setActiveTab("sql")}
          >
            执行 SQL
          </button>
          <span className="editor-row-count">
            {activeTab === "sql"
              ? sqlResult?.message || ""
              : loading || tableLoading
              ? "加载中..."
              : `${Math.min(totalRows, safePageIndex * pageSize + 1)} - ${Math.min(totalRows, (safePageIndex + 1) * pageSize)} / ${totalRows} 行${pendingChangeCount ? `，未写入 ${pendingChangeCount}` : ""}`}
          </span>
        </div>

        {activeTab === "browse" ? (
          <div className="editor-toolbar db-browser-toolbar">
          <label className="editor-toolbar-field table-picker" htmlFor="editor-table-select">
            <span>表</span>
            <select
              id="editor-table-select"
              className="editor-toolbar-select"
              value={selectedTable}
              onChange={(event) => changeTable(event.target.value)}
            >
              {tableSchema.tables.map((table) => (
                <option key={table.name} value={table.name}>
                  {table.label} ({table.row_count})
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            className="editor-tool-button"
            onClick={() => {
              if (pendingChangeCount && !window.confirm("当前有未写入的更改。刷新会放弃这些更改，是否继续？")) {
                return;
              }
              setPendingEdits({});
              setEditHistory([]);
              setColumnFilters((current) => ({ ...current }));
            }}
          >
            刷新
          </button>
          <button
            type="button"
            className="editor-tool-button"
            onClick={writePendingChanges}
            disabled={!pendingChangeCount || tableLoading}
          >
            写入更改
          </button>
          <button
            type="button"
            className="editor-tool-button"
            onClick={discardPendingChanges}
            disabled={!pendingChangeCount || tableLoading}
          >
            放弃更改
          </button>
          <button
            type="button"
            className="editor-tool-button"
            onClick={undoLastEdit}
            disabled={editHistory.length === 0 || tableLoading}
          >
            撤销
          </button>
          <button type="button" className="editor-tool-button" onClick={clearFilters}>
            清空筛选
          </button>

          <div className="editor-pager">
            <button
              type="button"
              className="editor-tool-button"
              onClick={() => setPageIndex(0)}
              disabled={safePageIndex <= 0}
            >
              首页
            </button>
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
            <button
              type="button"
              className="editor-tool-button"
              onClick={() => setPageIndex(pageCount - 1)}
              disabled={safePageIndex >= pageCount - 1}
            >
              尾页
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

          {isRecipeTable ? (
            <button type="button" className="editor-tool-button primary" onClick={openCreateModal}>
              新建条目
            </button>
          ) : null}
          </div>
        ) : null}

        {error ? <div className="error-banner editor-inline-banner">{error}</div> : null}
        {message ? <div className="editor-success-banner editor-inline-banner">{message}</div> : null}

        {activeTab === "sql" ? (
          <div className="sql-editor-pane">
            <div className="sql-editor-toolbar">
              <button type="button" className="editor-tool-button primary" onClick={runSql} disabled={sqlRunning || !sqlText.trim()}>
                {sqlRunning ? "执行中" : "执行 SQL"}
              </button>
              <button type="button" className="editor-tool-button" onClick={() => setSqlText("")}>
                清空
              </button>
            </div>
            <textarea
              className="sql-editor-input"
              value={sqlText}
              onChange={(event) => setSqlText(event.target.value)}
              spellCheck={false}
              aria-label="SQL 输入"
            />
            {sqlResult?.kind === "rows" ? (
              <div className="table-shell editor-table-shell sql-result-shell">
                <table className="preview-table editor-table db-browser-table sql-result-table">
                  <colgroup>
                    <col style={{ width: ROW_NUMBER_COLUMN_WIDTH }} />
                    {sqlResult.columns.map((column) => (
                      <col key={column} style={{ width: sqlColumnWidths[column] || initialColumnWidth(column) }} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="editor-row-number-column">#</th>
                      {sqlResult.columns.map((column) => (
                        <th key={column} className="db-resizable-header">
                          {column}
                          <span
                            className="db-column-resizer"
                            onMouseDown={(event) => startColumnResize("sql", column, sqlColumnWidths[column] || initialColumnWidth(column), event)}
                            role="separator"
                            aria-label={`调整 ${column} 列宽`}
                          />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sqlResult.items.map((row, rowIndex) => (
                      <tr key={`sql-row-${rowIndex}`}>
                        <td className="editor-row-number-column">{rowIndex + 1}</td>
                        {sqlResult.columns.map((column) => (
                          <td key={`${rowIndex}-${column}`}>
                            <span className="editor-readonly-cell">{displayValue(row[column])}</span>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="table-shell editor-table-shell db-browser-table-shell">
          <table className="preview-table editor-table db-browser-table">
            <colgroup>
              <col style={{ width: ROW_NUMBER_COLUMN_WIDTH }} />
              {isRecipeTable ? <col style={{ width: ACTION_COLUMN_WIDTH }} /> : null}
              {columns.map((column) => (
                <col key={column.name} style={{ width: columnWidths[column.name] || initialColumnWidth(column.name, column.type) }} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th className="editor-row-number-column">#</th>
                {isRecipeTable ? <th className="editor-action-column">操作</th> : null}
                {columns.map((column) => (
                  <th key={column.name} className="db-resizable-header">
                    <div className="db-column-title">{column.name}</div>
                    <div className="db-column-type">
                      {column.type || "TEXT"}
                      {column.primary_key ? " PK" : ""}
                    </div>
                    <span
                      className="db-column-resizer"
                      onMouseDown={(event) =>
                        startColumnResize(
                          "browse",
                          column.name,
                          columnWidths[column.name] || initialColumnWidth(column.name, column.type),
                          event
                        )
                      }
                      role="separator"
                      aria-label={`调整 ${column.name} 列宽`}
                    />
                  </th>
                ))}
              </tr>
              <tr className="db-filter-row">
                <th />
                {isRecipeTable ? <th /> : null}
                {columns.map((column) => (
                  <th key={`${column.name}-filter`}>
                    <input
                      type="search"
                      value={columnFilters[column.name] || ""}
                      onChange={(event) => updateColumnFilter(column.name, event.target.value)}
                      placeholder="过滤"
                      aria-label={`过滤 ${column.name}`}
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`${selectedTable}-${safePageIndex}-${rowIndex}`}>
                  <td className="editor-row-number-column">{safePageIndex * pageSize + rowIndex + 1}</td>
                  {isRecipeTable ? (
                    <td className="editor-action-column">
                      <button
                        type="button"
                        className="action-button compact"
                        onClick={() => openEditModal(row)}
                      >
                        修改
                      </button>
                    </td>
                  ) : null}
                  {columns.map((column) => (
                    <td
                      key={`${rowIndex}-${column.name}`}
                      className={
                        rowEditKey(row, columns) &&
                        Object.prototype.hasOwnProperty.call(pendingEdits[rowEditKey(row, columns)]?.values || {}, column.name)
                          ? "editor-dirty-cell"
                          : ""
                      }
                    >
                      {column.primary_key || !canEditSelectedTable ? (
                        <span className="editor-readonly-cell">{displayValue(row[column.name])}</span>
                      ) : (
                        <input
                          className="editor-cell-input"
                          value={normalizeEditableValue(getDisplayedCellValue(row, column.name))}
                          onChange={(event) => stageCellEdit(row, column, event.target.value)}
                          aria-label={`${column.name} 单元格`}
                        />
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}

        {activeTab === "browse" && !tableLoading && rows.length === 0 ? (
          <div className="empty-state compact-empty-state editor-empty-state">
            <p>当前表或筛选条件下没有数据。</p>
          </div>
        ) : null}

        {modalMode ? (
          <EditorFormModal
            mode={modalMode}
            fields={modalFields}
            options={recipeSchema.options}
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
