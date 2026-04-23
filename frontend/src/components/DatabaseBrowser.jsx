import { useEffect, useState } from "react";

import {
  exportDatabase,
  fetchDatabaseTableRows,
  fetchDatabaseTables,
  importDatabase,
} from "../lib/api";

const PAGE_SIZE = 50;

function formatCellValue(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export default function DatabaseBrowser() {
  const [tables, setTables] = useState([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [tableData, setTableData] = useState(null);
  const [listLoading, setListLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [transferLoading, setTransferLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [offset, setOffset] = useState(0);

  async function loadTables() {
    setListLoading(true);
    setError("");

    try {
      const result = await fetchDatabaseTables();
      setTables(result.items);
      setSelectedTable((current) => {
        if (current && result.items.some((item) => item.name === current)) {
          return current;
        }
        return result.items[0]?.name ?? "";
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    let active = true;

    async function load() {
      if (!active) {
        return;
      }
      await loadTables();
    }

    load();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadTableData() {
      if (!selectedTable) {
        setTableData(null);
        return;
      }

      setTableLoading(true);
      setError("");

      try {
        const result = await fetchDatabaseTableRows(selectedTable, { limit: PAGE_SIZE, offset });
        if (active) {
          setTableData(result);
        }
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

    loadTableData();

    return () => {
      active = false;
    };
  }, [selectedTable, offset]);

  async function handleExportDatabase() {
    setTransferLoading(true);
    setError("");
    setSuccessMessage("");
    try {
      await exportDatabase();
      setSuccessMessage("数据库下载已开始。");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setTransferLoading(false);
    }
  }

  async function handleImportDatabase(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    const confirmed = window.confirm("导入数据库会替换当前本地数据库，并自动备份旧库。是否继续？");
    if (!confirmed) {
      return;
    }

    setTransferLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      const result = await importDatabase(file);
      await loadTables();
      setOffset(0);
      setSuccessMessage(
        result.backup_file
          ? `数据库导入完成，旧库已备份为 ${result.backup_file}。`
          : "数据库导入完成。"
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setTransferLoading(false);
    }
  }

  const totalRows = tableData?.total_rows ?? 0;
  const currentStart = totalRows === 0 ? 0 : offset + 1;
  const currentEnd = Math.min(offset + PAGE_SIZE, totalRows);
  const canGoPrev = offset > 0;
  const canGoNext = offset + PAGE_SIZE < totalRows;

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Database Browser</p>
          <h2>查看数据库</h2>
        </div>
        <div className="action-row">
          <button
            type="button"
            className="action-button secondary"
            onClick={handleExportDatabase}
            disabled={transferLoading}
          >
            导出数据库
          </button>
          <label className={`action-button ${transferLoading ? "disabled-upload" : ""}`}>
            导入数据库
            <input
              type="file"
              accept=".db,.sqlite,.sqlite3"
              onChange={handleImportDatabase}
              disabled={transferLoading}
              hidden
            />
          </label>
        </div>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}
      {successMessage ? <div className="success-banner">{successMessage}</div> : null}

      <div className="history-layout database-layout">
        <div className="history-list">
          {listLoading ? <p className="recipe-meta">正在读取数据表...</p> : null}
          {!listLoading &&
            tables.map((table) => (
              <button
                key={table.name}
                type="button"
                className={selectedTable === table.name ? "history-card active" : "history-card"}
                onClick={() => {
                  setSelectedTable(table.name);
                  setOffset(0);
                }}
              >
                <div className="history-card-header">
                  <strong>{table.name}</strong>
                  <span>{table.row_count} 行</span>
                </div>
                <p>{table.column_count} 列</p>
                <div className="tag-row compact-tag-row">
                  {table.primary_key ? <span className="tag">主键 {table.primary_key}</span> : null}
                </div>
              </button>
            ))}
        </div>

        <div className="history-detail">
          {!selectedTable ? (
            <div className="empty-state compact-empty-state">
              <h3>没有可浏览的数据表</h3>
            </div>
          ) : null}

          {selectedTable && tableLoading ? (
            <div className="empty-state compact-empty-state">
              <h3>正在读取 {selectedTable}</h3>
            </div>
          ) : null}

          {selectedTable && !tableLoading && tableData ? (
            <div className="section-stack">
              <div className="import-summary-grid import-summary-grid-wide">
                <div className="detail-stat">
                  <span>数据表</span>
                  <strong>{tableData.table_name}</strong>
                </div>
                <div className="detail-stat">
                  <span>总行数</span>
                  <strong>{tableData.total_rows}</strong>
                </div>
                <div className="detail-stat">
                  <span>列数</span>
                  <strong>{tableData.columns.length}</strong>
                </div>
                <div className="detail-stat">
                  <span>当前范围</span>
                  <strong>
                    {currentStart}-{currentEnd}
                  </strong>
                </div>
              </div>

              <section className="detail-section">
                <h3>字段信息</h3>
                <div className="tag-row">
                  {tableData.columns.map((column) => (
                    <span key={column.name} className="tag">
                      {column.name} ({column.type})
                      {column.is_primary_key ? " PK" : ""}
                    </span>
                  ))}
                </div>
              </section>

              <section className="detail-section">
                <div className="panel-header database-toolbar">
                  <h3>表格数据</h3>
                  <div className="action-row">
                    <button
                      type="button"
                      className="action-button secondary"
                      disabled={!canGoPrev}
                      onClick={() => setOffset((current) => Math.max(current - PAGE_SIZE, 0))}
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      className="action-button secondary"
                      disabled={!canGoNext}
                      onClick={() => setOffset((current) => current + PAGE_SIZE)}
                    >
                      下一页
                    </button>
                  </div>
                </div>

                <div className="table-shell">
                  <table className="preview-table database-table">
                    <thead>
                      <tr>
                        {tableData.columns.map((column) => (
                          <th key={column.name}>{column.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {tableData.items.length === 0 ? (
                        <tr>
                          <td colSpan={tableData.columns.length || 1}>没有数据。</td>
                        </tr>
                      ) : (
                        tableData.items.map((row, rowIndex) => (
                          <tr key={`${tableData.table_name}-${offset + rowIndex}`}>
                            {tableData.columns.map((column) => (
                              <td key={`${offset + rowIndex}-${column.name}`} title={formatCellValue(row[column.name])}>
                                {formatCellValue(row[column.name])}
                              </td>
                            ))}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
