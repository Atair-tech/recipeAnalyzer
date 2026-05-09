import { useState } from "react";

function isManagementSection(sectionKey) {
  return ["tagging", "imports", "ingredientAnalysis", "refineReview", "pairing", "database", "aiLogs"].includes(sectionKey);
}

export default function Sidebar({ selectedSection, onSelectSection }) {
  const [managementExpanded, setManagementExpanded] = useState(false);

  const primarySections = [
    { key: "analytics", label: "\u603b\u89c8" },
    { key: "recipes", label: "\u83dc\u8c31\u5e93" },
    { key: "ai", label: "\u667a\u80fd\u95ee\u7b54" }
  ];

  const managementSections = [
    { key: "tagging", label: "标签管理" },
    { key: "imports", label: "导入 Excel" },
    { key: "ingredientAnalysis", label: "AI 分析食材" },
    { key: "pairing", label: "菜谱配对" },
    { key: "database", label: "查看数据库" },
    { key: "aiLogs", label: "AI 对话记录" },
    { key: "refineReview", label: "食材审查" }
  ];

  return (
    <aside className="sidebar">
      <div className="brand-block">
        <div className="brand-mark" aria-hidden="true">
          <div className="brand-mark-frame">
            <span className="brand-mark-plate" />
            <span className="brand-mark-meat" />
            <span className="brand-mark-egg" />
            <span className="brand-mark-greens" />
            <span className="brand-mark-greens brand-mark-greens-right" />
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
    </aside>
  );
}
