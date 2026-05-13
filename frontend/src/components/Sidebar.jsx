import { useState } from "react";

function isManagementSection(sectionKey) {
  return ["tagging", "imports", "ingredientAnalysis", "refineReview", "pairing", "database", "settings", "aiLogs"].includes(sectionKey);
}

export default function Sidebar({ selectedSection, onSelectSection }) {
  const [managementExpanded, setManagementExpanded] = useState(false);

  const primarySections = [
    { key: "analytics", label: "\u603b\u89c8" },
    { key: "recipes", label: "\u83dc\u8c31\u5e93" },
    { key: "ai", label: "\u667a\u80fd\u95ee\u7b54" }
  ];

  const managementSections = [
    { key: "tagging", label: "\u6807\u7b7e\u7ba1\u7406" },
    { key: "imports", label: "\u5bfc\u5165 Excel" },
    { key: "ingredientAnalysis", label: "AI \u5206\u6790\u98df\u6750" },
    { key: "pairing", label: "\u83dc\u8c31\u914d\u5bf9" },
    { key: "database", label: "\u67e5\u770b\u6570\u636e\u5e93" },
    { key: "settings", label: "\u7cfb\u7edf\u8bbe\u7f6e" },
    { key: "aiLogs", label: "AI \u5bf9\u8bdd\u8bb0\u5f55" },
    { key: "refineReview", label: "\u98df\u6750\u5ba1\u67e5" }
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
            <span className="nav-group-arrow">{managementExpanded ? "▴" : "▾"}</span>
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
