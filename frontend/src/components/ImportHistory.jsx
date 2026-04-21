import { useEffect, useState } from "react";

import { fetchImportBatchDetail, fetchImportBatches } from "../lib/api";

export default function ImportHistory({ reloadToken }) {
  const [batches, setBatches] = useState([]);
  const [selectedBatchId, setSelectedBatchId] = useState(null);
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadBatches() {
      setListLoading(true);
      setError("");

      try {
        const batchData = await fetchImportBatches();
        if (!active) {
          return;
        }

        setBatches(batchData.items);
        setSelectedBatchId((current) => {
          const stillExists = batchData.items.some((item) => item.id === current);
          return stillExists ? current : batchData.items[0]?.id ?? null;
        });
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      } finally {
        if (active) {
          setListLoading(false);
        }
      }
    }

    loadBatches();

    return () => {
      active = false;
    };
  }, [reloadToken]);

  useEffect(() => {
    let active = true;

    async function loadBatchDetail() {
      if (!selectedBatchId) {
        setSelectedBatch(null);
        return;
      }

      setDetailLoading(true);
      setError("");

      try {
        const batchDetail = await fetchImportBatchDetail(selectedBatchId, 15);
        if (active) {
          setSelectedBatch(batchDetail);
        }
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      } finally {
        if (active) {
          setDetailLoading(false);
        }
      }
    }

    loadBatchDetail();

    return () => {
      active = false;
    };
  }, [selectedBatchId]);

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Import history</p>
          <h2>查看每次同步批次</h2>
        </div>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="history-layout">
        <div className="history-list">
          {listLoading ? <p className="recipe-meta">加载批次中...</p> : null}
          {!listLoading && batches.length === 0 ? <p className="recipe-meta">还没有同步批次。</p> : null}
          {batches.map((batch) => (
            <button
              key={batch.id}
              type="button"
              className={selectedBatchId === batch.id ? "history-card active" : "history-card"}
              onClick={() => setSelectedBatchId(batch.id)}
            >
              <div className="history-card-header">
                <strong>批次 #{batch.id}</strong>
                <span>{batch.raw_row_count} 条</span>
              </div>
              <h3>{batch.file_name}</h3>
              <p>{batch.imported_at}</p>
              <div className="tag-row compact-tag-row">
                <span className="tag">正式菜谱 {batch.recipe_records}</span>
                <span className="tag muted">待办 {batch.backlog_records}</span>
                {batch.index_only_recipes ? <span className="tag muted">仅索引 {batch.index_only_recipes}</span> : null}
                {batch.detail_only_recipes ? <span className="tag muted">仅做法 {batch.detail_only_recipes}</span> : null}
              </div>
            </button>
          ))}
        </div>

        <div className="history-detail">
          {detailLoading ? (
            <div className="empty-state compact-empty-state">
              <h3>加载批次详情中</h3>
            </div>
          ) : null}

          {!detailLoading && !selectedBatch ? (
            <div className="empty-state compact-empty-state">
              <h3>未选择批次</h3>
              <p>从左侧选择一个批次查看解析结果。</p>
            </div>
          ) : null}

          {!detailLoading && selectedBatch ? (
            <>
              <div className="import-summary-grid import-summary-grid-wide">
                <div className="detail-stat">
                  <span>导入时间</span>
                  <strong>{selectedBatch.imported_at}</strong>
                </div>
                <div className="detail-stat">
                  <span>原始记录数</span>
                  <strong>{selectedBatch.raw_row_count}</strong>
                </div>
                <div className="detail-stat">
                  <span>解析器</span>
                  <strong>{selectedBatch.parser_kind || "未知"}</strong>
                </div>
                <div className="detail-stat">
                  <span>正式菜谱</span>
                  <strong>{selectedBatch.summary?.recipe_records ?? 0}</strong>
                </div>
                <div className="detail-stat">
                  <span>待办项</span>
                  <strong>{selectedBatch.summary?.backlog_records ?? 0}</strong>
                </div>
                <div className="detail-stat">
                  <span>仅做法页</span>
                  <strong>{selectedBatch.summary?.detail_only_recipes ?? 0}</strong>
                </div>
              </div>

              <section className="detail-section">
                <h3>工作表</h3>
                <div className="tag-row">
                  {(selectedBatch.sheet_names ?? []).map((sheetName) => (
                    <span key={sheetName} className="tag">
                      {sheetName}
                    </span>
                  ))}
                </div>
              </section>

              <section className="detail-section">
                <h3>预览记录</h3>
                <div className="table-shell">
                  <table className="preview-table">
                    <thead>
                      <tr>
                        <th>序号</th>
                        {selectedBatch.fields.map((field) => (
                          <th key={field.key}>{field.label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedBatch.rows.map((row) => (
                        <tr key={row.id}>
                          <td>{row.row_index}</td>
                          {selectedBatch.fields.map((field) => (
                            <td key={`${row.id}-${field.key}`}>{row.mapped_row?.[field.key] ?? ""}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
