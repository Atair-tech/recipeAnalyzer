import { useState } from "react";

import { commitImport, previewImport } from "../lib/api";

function SummaryCards({ preview }) {
  const summary = preview?.summary ?? {};

  return (
    <div className="import-summary-grid import-summary-grid-wide">
      <div className="detail-stat">
        <span>总记录数</span>
        <strong>{summary.total_records ?? 0}</strong>
      </div>
      <div className="detail-stat">
        <span>正式菜谱</span>
        <strong>{summary.recipe_records ?? 0}</strong>
      </div>
      <div className="detail-stat">
        <span>待办项</span>
        <strong>{summary.backlog_records ?? 0}</strong>
      </div>
      <div className="detail-stat">
        <span>已配对条目</span>
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
    </div>
  );
}

export default function ImportWorkspace({ onImportCommitted }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [commitLoading, setCommitLoading] = useState(false);
  const [error, setError] = useState("");

  async function handlePreview() {
    if (!selectedFile) {
      return;
    }

    setPreviewLoading(true);
    setError("");
    setResult(null);

    try {
      const previewData = await previewImport(selectedFile);
      setPreview(previewData);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handleCommit() {
    if (!selectedFile) {
      return;
    }

    setCommitLoading(true);
    setError("");

    try {
      const importResult = await commitImport(selectedFile);
      setResult(importResult);
      onImportCommitted();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setCommitLoading(false);
    }
  }

  return (
    <section className="panel import-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Excel import</p>
          <h2>按真实工作簿结构同步</h2>
        </div>
      </div>

      <div className="warning-banner">
        当前导入器基于这份真实工作簿的结构工作，会自动识别“索引页 + 做法页 + 甜点页 + 待办页”，并按差异同步数据库。
      </div>

      <div className="import-controls">
        <label className="file-shell" htmlFor="excel-file">
          <span>Excel 文件</span>
          <input
            id="excel-file"
            type="file"
            accept=".xlsx"
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              setSelectedFile(file);
              setPreview(null);
              setResult(null);
              setError("");
            }}
          />
        </label>

        <div className="action-row">
          <button
            type="button"
            className="action-button secondary"
            onClick={handlePreview}
            disabled={!selectedFile || previewLoading || commitLoading}
          >
            {previewLoading ? "解析中..." : "预览结构"}
          </button>
          <button
            type="button"
            className="action-button"
            onClick={handleCommit}
            disabled={!selectedFile || !preview || previewLoading || commitLoading}
          >
            {commitLoading ? "同步中..." : "同步到 SQLite"}
          </button>
        </div>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      {result ? (
        <div className="success-banner">
          已完成批次 #{result.batch_id}。新增 {result.added_recipes}，更新 {result.updated_recipes}，删除{" "}
          {result.deleted_recipes}，未变化 {result.unchanged_recipes}。
        </div>
      ) : null}

      {preview ? (
        <div className="import-preview">
          <SummaryCards preview={preview} />

          <section className="detail-section">
            <h3>工作簿概览</h3>
            <div className="tag-row">
              {(preview.sheet_names ?? []).map((sheetName) => (
                <span key={sheetName} className="tag">
                  {sheetName}
                </span>
              ))}
            </div>
          </section>

          <section className="detail-section">
            <h3>专题库分布</h3>
            <div className="tag-row">
              {(preview.summary?.library_sections ?? []).map((item) => (
                <span key={item.label} className="tag">
                  {item.label}: {item.value}
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
                    {preview.fields.map((field) => (
                      <th key={field.key}>{field.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.preview_rows.map((row, index) => (
                    <tr key={`preview-row-${index}`}>
                      {preview.fields.map((field) => (
                        <td key={`${index}-${field.key}`}>{row[field.key] ?? ""}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : (
        <div className="empty-state">
          <h3>等待解析</h3>
          <p>请选择 `data/recipes.xlsx` 这类真实工作簿，先解析结构，再执行同步。</p>
        </div>
      )}
    </section>
  );
}
