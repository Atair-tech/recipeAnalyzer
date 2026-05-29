import { useEffect, useMemo, useState } from "react";

import {
  applyRecipeEditorTableChanges,
  createRecipeEditorRow,
  executeRecipeEditorSql,
  fetchRecipeEditorSchema,
  fetchRecipeEditorTableRows,
  fetchRecipeEditorTables,
  fetchRecipeEditorUserViewFilterValues,
  fetchRecipeEditorUserViewRows,
  fetchRecipeEditorUserViews,
  updateRecipeEditorRow
} from "../lib/api";

const RECORD_KIND_LABELS = {
  recipe: "正式菜谱",
  backlog: "待办条目"
};

const MIN_COLUMN_WIDTH = 34;
const ROW_NUMBER_COLUMN_WIDTH = 48;
const ACTION_COLUMN_WIDTH = 72;
const USER_VIEW_COLUMN_WIDTHS = {
  菜名: 90,
  主题: 70,
  分组: 70,
  大地域: 56,
  细分地域: 64,
  食材: 90,
  调料: 90,
  做法与要点: 104,
  "来源/修订备注": 92,
  最后记录日期: 86,
  BMD: 42,
  CC: 42,
  "自动标签（参考）": 100,
  "标准食材（参考）": 100,
  记录类型: 70,
  待办状态: 70,
  标准食材: 120,
  可见: 64,
  关联菜谱数: 108,
  别名: 120,
  标签: 100,
  说明: 260,
  排序: 46,
};

function initialColumnWidth(columnName, columnType = "") {
  const labelWidth = Math.max(MIN_COLUMN_WIDTH, columnName.length * 14 + 28);
  if (USER_VIEW_COLUMN_WIDTHS[columnName]) {
    return Math.max(USER_VIEW_COLUMN_WIDTHS[columnName], labelWidth);
  }
  const normalizedType = String(columnType || "").toUpperCase();
  if (columnName === "id" || columnName.endsWith("_id") || columnName === "run_id") {
    return Math.max(82, labelWidth);
  }
  if (columnName.endsWith("_flag") || columnName === "is_visible" || columnName === "is_active") {
    return Math.max(76, labelWidth);
  }
  if (columnName.includes("hash")) {
    return Math.max(240, labelWidth);
  }
  if (columnName.includes("json") || columnName.includes("raw_response") || columnName.includes("source_text")) {
    return Math.max(360, labelWidth);
  }
  if (columnName.includes("text") || columnName.includes("message") || columnName.includes("reason") || columnName.includes("error")) {
    return Math.max(280, labelWidth);
  }
  if (columnName.endsWith("_at") || columnName.endsWith("_on") || columnName.includes("date") || columnName.includes("time")) {
    return Math.max(170, labelWidth);
  }
  if (columnName === "name" || columnName.endsWith("_name") || columnName === "model") {
    return Math.max(180, labelWidth);
  }
  if (normalizedType.includes("INTEGER") || normalizedType.includes("REAL")) {
    return Math.max(96, labelWidth);
  }
  return Math.max(150, labelWidth);
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

function displayText(value) {
  if (value === null || value === undefined) {
    return "NULL";
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
  const [userViewSchema, setUserViewSchema] = useState({ views: [], default_view: "" });
  const [selectedTable, setSelectedTable] = useState("");
  const [selectedUserView, setSelectedUserView] = useState("");
  const [rows, setRows] = useState([]);
  const [userRows, setUserRows] = useState([]);
  const [totalRows, setTotalRows] = useState(0);
  const [userTotalRows, setUserTotalRows] = useState(0);
  const [columnFilters, setColumnFilters] = useState({});
  const [userColumnFilters, setUserColumnFilters] = useState({});
  const [pageIndex, setPageIndex] = useState(0);
  const [userPageIndex, setUserPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(100);
  const [userPageSize, setUserPageSize] = useState(100);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [userViewLoading, setUserViewLoading] = useState(false);
  const [savingId, setSavingId] = useState(null);
  const [modalMode, setModalMode] = useState(null);
  const [modalRecipeId, setModalRecipeId] = useState(null);
  const [modalValues, setModalValues] = useState({});
  const [activeTab, setActiveTab] = useState("user");
  const [sqlText, setSqlText] = useState("SELECT * FROM recipes LIMIT 50;");
  const [sqlResult, setSqlResult] = useState(null);
  const [sqlRunning, setSqlRunning] = useState(false);
  const [columnWidths, setColumnWidths] = useState({});
  const [userColumnWidths, setUserColumnWidths] = useState({});
  const [sqlColumnWidths, setSqlColumnWidths] = useState({});
  const [userFilterMenu, setUserFilterMenu] = useState(null);
  const [userFilterValues, setUserFilterValues] = useState([]);
  const [userFilterSelection, setUserFilterSelection] = useState([]);
  const [userFilterSearch, setUserFilterSearch] = useState("");
  const [userFilterLoading, setUserFilterLoading] = useState(false);
  const [userSort, setUserSort] = useState({ column: "", direction: "" });
  const [userCellPopover, setUserCellPopover] = useState(null);
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
        let userViewSchemaData = { views: [], default_view: "" };
        try {
          userViewSchemaData = await fetchRecipeEditorUserViews();
        } catch {
          // Older running backends may not expose user-view APIs yet. Keep the
          // existing browse/SQL tabs usable until the backend is restarted.
          userViewSchemaData = { views: [], default_view: "" };
        }
        if (!active) {
          return;
        }
        setRecipeSchema(recipeSchemaData);
        setTableSchema(tableSchemaData);
        setUserViewSchema(userViewSchemaData);
        setSelectedTable(tableSchemaData.default_table || tableSchemaData.tables[0]?.name || "");
        setSelectedUserView(userViewSchemaData.default_view || userViewSchemaData.views[0]?.name || "");
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
  const selectedUserViewInfo = useMemo(
    () => userViewSchema.views.find((view) => view.name === selectedUserView) || null,
    [selectedUserView, userViewSchema.views]
  );
  const columns = selectedTableInfo?.columns || [];
  const userColumns = selectedUserViewInfo?.columns || [];
  const modalFields = useMemo(() => {
    const columnNames = new Set(columns.map((column) => column.name));
    return recipeSchema.fields.filter((field) => columnNames.has(field.key));
  }, [columns, recipeSchema.fields]);
  const pageCount = Math.max(1, Math.ceil(totalRows / pageSize));
  const safePageIndex = Math.min(pageIndex, pageCount - 1);
  const userPageCount = Math.max(1, Math.ceil(userTotalRows / userPageSize));
  const safeUserPageIndex = Math.min(userPageIndex, userPageCount - 1);
  const isRecipeTable = selectedTable === "recipes";
  const pendingChangeCount = useMemo(
    () => Object.values(pendingEdits).reduce((total, rowEdits) => total + Object.keys(rowEdits.values || {}).length, 0),
    [pendingEdits]
  );
  const canEditSelectedTable = columns.some((column) => column.primary_key);
  const userViewTableWidth = useMemo(
    () =>
      ROW_NUMBER_COLUMN_WIDTH +
      userColumns.reduce(
        (total, column) => total + (userColumnWidths[column.name] || initialColumnWidth(column.name, column.type)),
        0
      ),
    [userColumns, userColumnWidths]
  );

  useEffect(() => {
    setColumnWidths(buildInitialColumnWidths(columns));
  }, [selectedTable, columns]);

  useEffect(() => {
    setUserColumnWidths(buildInitialColumnWidths(userColumns));
  }, [selectedUserView, userColumns]);

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
    if (!selectedUserView) {
      return;
    }

    let active = true;
    async function loadUserRows() {
      setUserViewLoading(true);
      setError("");
      try {
        const data = await fetchRecipeEditorUserViewRows({
          view: selectedUserView,
          filters: userColumnFilters,
          limit: userPageSize,
          offset: safeUserPageIndex * userPageSize,
          sortColumn: userSort.column,
          sortDirection: userSort.direction
        });
        if (!active) {
          return;
        }
        setUserRows(data.items);
        setUserTotalRows(data.total);
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      } finally {
        if (active) {
          setUserViewLoading(false);
        }
      }
    }

    loadUserRows();
    return () => {
      active = false;
    };
  }, [selectedUserView, userColumnFilters, userPageSize, safeUserPageIndex, userSort]);

  useEffect(() => {
    setPageIndex(0);
  }, [columnFilters, pageSize, selectedTable]);

  useEffect(() => {
    setUserPageIndex(0);
  }, [userColumnFilters, userPageSize, selectedUserView, userSort]);

  useEffect(() => {
    if (!userFilterMenu || !selectedUserView) {
      return;
    }

    let active = true;
    async function loadFilterValues() {
      setUserFilterLoading(true);
      try {
        const data = await fetchRecipeEditorUserViewFilterValues({
          view: selectedUserView,
          column: userFilterMenu.column,
          filters: userColumnFilters,
          search: userFilterSearch
        });
        if (!active) {
          return;
        }
        const values = data.values || [];
        setUserFilterValues(values);
        const activeFilter = userColumnFilters[userFilterMenu.column];
        if (Array.isArray(activeFilter)) {
          setUserFilterSelection(activeFilter.map((value) => String(value)));
        } else {
          setUserFilterSelection(values);
        }
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
          setUserFilterValues([]);
          setUserFilterSelection([]);
        }
      } finally {
        if (active) {
          setUserFilterLoading(false);
        }
      }
    }

    loadFilterValues();
    return () => {
      active = false;
    };
  }, [selectedUserView, userFilterMenu, userFilterSearch, userColumnFilters]);

  useEffect(() => {
    if (!userCellPopover) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (event.target.closest(".user-cell-popover")) {
        return;
      }
      setUserCellPopover(null);
    }

    window.addEventListener("pointerdown", handlePointerDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [userCellPopover]);

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

  function updateUserColumnFilter(columnName, value) {
    setUserColumnFilters((current) => {
      const next = { ...current };
      if (value.trim()) {
        next[columnName] = value;
      } else {
        delete next[columnName];
      }
      return next;
    });
  }

  function clearUserFilters() {
    setUserColumnFilters({});
    setUserSort({ column: "", direction: "" });
    setUserFilterMenu(null);
    setUserCellPopover(null);
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

  function changeUserView(viewName) {
    setSelectedUserView(viewName);
    setUserColumnFilters({});
    setUserSort({ column: "", direction: "" });
    setUserFilterMenu(null);
    setUserCellPopover(null);
    setUserRows([]);
    setUserTotalRows(0);
    setMessage("");
    setError("");
  }

  function openUserFilterMenu(columnName, event) {
    event.preventDefault();
    event.stopPropagation();
    setUserCellPopover(null);
    if (userFilterMenu?.column === columnName) {
      setUserFilterMenu(null);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    setUserFilterSearch("");
    setUserFilterValues([]);
    setUserFilterSelection([]);
    setUserFilterMenu({
      column: columnName,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - 340)),
      top: rect.bottom + 2
    });
  }

  function toggleUserFilterValue(value) {
    setUserFilterSelection((current) => {
      if (current.includes(value)) {
        return current.filter((item) => item !== value);
      }
      return [...current, value];
    });
  }

  function toggleAllUserFilterValues() {
    setUserFilterSelection((current) => {
      const allVisibleSelected = userFilterValues.length > 0 && userFilterValues.every((value) => current.includes(value));
      if (allVisibleSelected) {
        return current.filter((value) => !userFilterValues.includes(value));
      }
      return Array.from(new Set([...current, ...userFilterValues]));
    });
  }

  function applyUserFilterMenu() {
    if (!userFilterMenu) {
      return;
    }
    const selected = userFilterSelection.map((value) => String(value));
    const hasSearchText = userFilterSearch.trim().length > 0;
    setUserColumnFilters((current) => {
      const next = { ...current };
      if (
        !hasSearchText &&
        selected.length === userFilterValues.length &&
        userFilterValues.every((value) => selected.includes(value))
      ) {
        delete next[userFilterMenu.column];
      } else {
        next[userFilterMenu.column] = selected;
      }
      return next;
    });
    setUserFilterMenu(null);
    setUserCellPopover(null);
  }

  function clearUserColumnFilter(columnName) {
    setUserColumnFilters((current) => {
      const next = { ...current };
      delete next[columnName];
      return next;
    });
    setUserFilterMenu(null);
    setUserCellPopover(null);
  }

  function sortUserView(columnName, direction) {
    setUserSort({ column: columnName, direction });
    setUserPageIndex(0);
    setUserFilterMenu(null);
    setUserCellPopover(null);
  }

  function openUserCellPopover(columnName, value, event) {
    const text = displayText(value);
    if (!text || text === "NULL") {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    setUserFilterMenu(null);
    setUserCellPopover({
      column: columnName,
      value: text,
      left: Math.max(8, Math.min(rect.left, window.innerWidth - 448)),
      top: Math.min(rect.bottom + 4, window.innerHeight - 260)
    });
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
    const setter = kind === "sql" ? setSqlColumnWidths : kind === "user" ? setUserColumnWidths : setColumnWidths;

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
            className={activeTab === "user" ? "editor-menu-tab active" : "editor-menu-tab"}
            onClick={() => setActiveTab("user")}
          >
            用户阅览
          </button>
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
              : activeTab === "user"
              ? loading || userViewLoading
                ? "加载中..."
                : `${userTotalRows ? safeUserPageIndex * userPageSize + 1 : 0} - ${Math.min(userTotalRows, (safeUserPageIndex + 1) * userPageSize)} / ${userTotalRows} 行`
              : loading || tableLoading
              ? "加载中..."
              : `${totalRows ? safePageIndex * pageSize + 1 : 0} - ${Math.min(totalRows, (safePageIndex + 1) * pageSize)} / ${totalRows} 行${pendingChangeCount ? `，未写入 ${pendingChangeCount}` : ""}`}
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

        {activeTab === "user" ? (
          <div className="editor-toolbar db-browser-toolbar user-view-toolbar">
            <label className="editor-toolbar-field table-picker" htmlFor="editor-user-view-select">
              <span>视图</span>
              <select
                id="editor-user-view-select"
                className="editor-toolbar-select"
                value={selectedUserView}
                onChange={(event) => changeUserView(event.target.value)}
              >
                {userViewSchema.views.map((view) => (
                  <option key={view.name} value={view.name}>
                    {view.label} ({view.row_count})
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              className="editor-tool-button"
              onClick={() => setUserColumnFilters((current) => ({ ...current }))}
            >
              刷新
            </button>
            <button type="button" className="editor-tool-button" onClick={clearUserFilters}>
              清空筛选
            </button>

            <div className="editor-pager">
              <button
                type="button"
                className="editor-tool-button"
                onClick={() => setUserPageIndex(0)}
                disabled={safeUserPageIndex <= 0}
              >
                首页
              </button>
              <button
                type="button"
                className="editor-tool-button"
                onClick={() => setUserPageIndex((current) => Math.max(0, current - 1))}
                disabled={safeUserPageIndex <= 0}
              >
                上一页
              </button>
              <button
                type="button"
                className="editor-tool-button"
                onClick={() => setUserPageIndex((current) => Math.min(userPageCount - 1, current + 1))}
                disabled={safeUserPageIndex >= userPageCount - 1}
              >
                下一页
              </button>
              <button
                type="button"
                className="editor-tool-button"
                onClick={() => setUserPageIndex(userPageCount - 1)}
                disabled={safeUserPageIndex >= userPageCount - 1}
              >
                尾页
              </button>
              <select
                className="editor-toolbar-select compact"
                value={String(userPageSize)}
                onChange={(event) => setUserPageSize(Number(event.target.value))}
                aria-label="用户阅览每页行数"
              >
                {[50, 100, 200, 500].map((value) => (
                  <option key={value} value={value}>
                    {value} 行
                  </option>
                ))}
              </select>
            </div>

            {selectedUserViewInfo?.description ? (
              <span className="user-view-description">{selectedUserViewInfo.description}</span>
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
        ) : activeTab === "user" ? (
          <div className="table-shell editor-table-shell db-browser-table-shell">
            <table
              className="preview-table editor-table db-browser-table user-view-table"
              style={{ width: userViewTableWidth, minWidth: userViewTableWidth }}
            >
              <colgroup>
                <col style={{ width: ROW_NUMBER_COLUMN_WIDTH }} />
                {userColumns.map((column) => (
                  <col key={column.name} style={{ width: userColumnWidths[column.name] || initialColumnWidth(column.name, column.type) }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  <th className="editor-row-number-column">序号</th>
                  {userColumns.map((column) => (
                    <th
                      key={column.name}
                      className={
                        userColumnFilters[column.name] || userSort.column === column.name
                          ? "db-resizable-header user-filtered-column"
                          : "db-resizable-header"
                      }
                    >
                      <div className="db-column-title user-filter-column-title">
                        <span>{column.name}</span>
                        {userSort.column === column.name ? (
                          <span className="user-sort-indicator">{userSort.direction === "desc" ? "↓" : "↑"}</span>
                        ) : null}
                        <button
                          type="button"
                          className="user-filter-trigger"
                          onClick={(event) => openUserFilterMenu(column.name, event)}
                          aria-label={`筛选 ${column.name}`}
                        >
                          ▾
                        </button>
                      </div>
                      <span
                        className="db-column-resizer"
                        onMouseDown={(event) =>
                          startColumnResize(
                            "user",
                            column.name,
                            userColumnWidths[column.name] || initialColumnWidth(column.name, column.type),
                            event
                          )
                        }
                        role="separator"
                        aria-label={`调整 ${column.name} 列宽`}
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {userRows.map((row, rowIndex) => (
                  <tr key={`${selectedUserView}-${safeUserPageIndex}-${rowIndex}`}>
                    <td className="editor-row-number-column">{safeUserPageIndex * userPageSize + rowIndex + 1}</td>
                    {userColumns.map((column) => (
                      <td key={`${rowIndex}-${column.name}`}>
                        <button
                          type="button"
                          className="editor-readonly-cell user-view-cell"
                          onClick={(event) => openUserCellPopover(column.name, row[column.name], event)}
                          title={displayText(row[column.name])}
                        >
                          {displayValue(row[column.name])}
                        </button>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
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

        {userFilterMenu ? (
          <div
            className="user-filter-popover"
            style={{ left: userFilterMenu.left, top: userFilterMenu.top }}
            role="dialog"
            aria-label={`${userFilterMenu.column} 筛选`}
          >
            <div className="user-filter-menu-row">
              <button
                type="button"
                className={userSort.column === userFilterMenu.column && userSort.direction === "asc" ? "user-filter-menu-command active" : "user-filter-menu-command"}
                onClick={() => sortUserView(userFilterMenu.column, "asc")}
              >
                升序
              </button>
              <button
                type="button"
                className={userSort.column === userFilterMenu.column && userSort.direction === "desc" ? "user-filter-menu-command active" : "user-filter-menu-command"}
                onClick={() => sortUserView(userFilterMenu.column, "desc")}
              >
                降序
              </button>
            </div>
            <input
              className="user-filter-search"
              type="search"
              value={userFilterSearch}
              onChange={(event) => setUserFilterSearch(event.target.value)}
              autoFocus
              aria-label={`${userFilterMenu.column} 筛选搜索`}
            />
            <div className="user-filter-values">
              <label className="user-filter-value">
                <input
                  type="checkbox"
                  checked={userFilterValues.length > 0 && userFilterValues.every((value) => userFilterSelection.includes(value))}
                  onChange={toggleAllUserFilterValues}
                />
                <span>(全选)</span>
              </label>
              {userFilterLoading ? (
                <div className="user-filter-loading">加载中...</div>
              ) : (
                userFilterValues.map((value) => (
                  <label key={value || "__blank__"} className="user-filter-value">
                    <input
                      type="checkbox"
                      checked={userFilterSelection.includes(value)}
                      onChange={() => toggleUserFilterValue(value)}
                    />
                    <span>{value || "(空白)"}</span>
                  </label>
                ))
              )}
            </div>
            <div className="user-filter-actions">
              <button type="button" className="editor-tool-button" onClick={() => clearUserColumnFilter(userFilterMenu.column)}>
                清除
              </button>
              <span />
              <button type="button" className="editor-tool-button primary" onClick={applyUserFilterMenu}>
                确定
              </button>
              <button type="button" className="editor-tool-button" onClick={() => setUserFilterMenu(null)}>
                取消
              </button>
            </div>
          </div>
        ) : null}

        {userCellPopover ? (
          <div
            className="user-cell-popover"
            style={{ left: userCellPopover.left, top: userCellPopover.top }}
            role="dialog"
            aria-label={`${userCellPopover.column} 完整内容`}
          >
            <header>
              <strong>{userCellPopover.column}</strong>
              <button type="button" className="icon-action-button" onClick={() => setUserCellPopover(null)} aria-label="关闭">
                ×
              </button>
            </header>
            <div className="user-cell-popover-content">{userCellPopover.value}</div>
          </div>
        ) : null}

        {activeTab === "browse" && !tableLoading && rows.length === 0 ? (
          <div className="empty-state compact-empty-state editor-empty-state">
            <p>当前表或筛选条件下没有数据。</p>
          </div>
        ) : null}

        {activeTab === "user" && !userViewLoading && userRows.length === 0 ? (
          <div className="empty-state compact-empty-state editor-empty-state">
            <p>{userViewSchema.views.length ? "当前视图或筛选条件下没有数据。" : "用户阅览接口未加载，请重启后端后再试。"}</p>
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
