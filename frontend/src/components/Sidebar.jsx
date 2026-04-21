import { useState } from "react";

function isManagementSection(sectionKey) {
  return ["tagging", "imports", "pairing", "database", "aiLogs"].includes(sectionKey);
}

export default function Sidebar({ health, overview, selectedSection, onSelectSection }) {
  const [managementExpanded, setManagementExpanded] = useState(false);

  const primarySections = [
    { key: "overview", label: "总览" },
    { key: "recipes", label: "菜谱库" },
    { key: "ai", label: "智能问答" },
    { key: "analytics", label: "数据分析" }
  ];

  const managementSections = [
    { key: "tagging", label: "标签管理" },
    { key: "imports", label: "导入 Excel" },
    { key: "pairing", label: "菜谱配对" },
    { key: "database", label: "查看数据库" },
    { key: "aiLogs", label: "AI 对话记录" }
  ];

  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark" aria-hidden="true">
          <div className="brand-mark-frame">
            <span className="brand-mark-book" />
            <span className="brand-mark-spoon" />
            <span className="brand-mark-leaf" />
          </div>
        </div>
        <div className="brand-title-group">
          <h1>Recipe Analyzer</h1>
        </div>
      </div>

      <nav className="nav-list" aria-label="Primary sections">
        {primarySections.map((section) => (
          <button
            key={section.key}
            type="button"
            className={selectedSection === section.key ? "nav-item active" : "nav-item"}
            onClick={() => onSelectSection(section.key)}
          >
            {section.label}
          </button>
        ))}

        <div className={isManagementSection(selectedSection) ? "nav-group active" : "nav-group"}>
          <button
            type="button"
            className="nav-group-trigger"
            onClick={() => setManagementExpanded((current) => !current)}
            aria-expanded={managementExpanded}
          >
            <span className="nav-group-title">管理</span>
            <span className="nav-group-arrow">{managementExpanded ? "▾" : "▸"}</span>
          </button>

          {managementExpanded ? (
            <div className="nav-sublist">
              {managementSections.map((section) => (
                <button
                  key={section.key}
                  type="button"
                  className={selectedSection === section.key ? "nav-item nav-subitem active" : "nav-item nav-subitem"}
                  onClick={() => onSelectSection(section.key)}
                >
                  {section.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </nav>

      <div className="status-card">
        <div className="status-row">
          <span>API</span>
          <strong className={health?.status === "ok" ? "status-ok" : "status-offline"}>
            {health?.status ?? "unknown"}
          </strong>
        </div>
        <div className="status-row">
          <span>正式菜谱</span>
          <strong>{overview?.recipe_count ?? 0}</strong>
        </div>
        <div className="status-row">
          <span>待办项</span>
          <strong>{overview?.backlog_count ?? 0}</strong>
        </div>
        <div className="status-row">
          <span>专题库</span>
          <strong>{overview?.library_section_count ?? 0}</strong>
        </div>
      </div>
    </aside>
  );
}
