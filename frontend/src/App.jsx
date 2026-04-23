import { startTransition, useDeferredValue, useEffect, useState } from "react";

import AnalyticsDashboard from "./components/AnalyticsDashboard";
import AiLogViewer from "./components/AiLogViewer";
import AITools from "./components/AITools";
import DatabaseBrowser from "./components/DatabaseBrowser";
import ImportHistory from "./components/ImportHistory";
import ImportRefinementPanel from "./components/ImportRefinementPanel";
import ImportWorkspace from "./components/ImportWorkspace";
import PairingReview from "./components/PairingReview";
import RefineReview from "./components/RefineReview";
import RecipeDetail from "./components/RecipeDetail";
import RecipeList from "./components/RecipeList";
import Sidebar from "./components/Sidebar";
import TagManagement from "./components/TagManagement";
import { fetchHealth, fetchOverview, fetchRecipe, fetchRecipeFilters, fetchRecipes } from "./lib/api";

function intersectOptions(primaryOptions, allowedOptions) {
  if (!allowedOptions || allowedOptions.length === 0) {
    return [];
  }
  const allowedSet = new Set(allowedOptions);
  return primaryOptions.filter((option) => allowedSet.has(option));
}

function OverviewSection({ overview }) {
  const cards = [
    {
      label: "正式菜谱",
      value: overview?.recipe_count ?? 0,
      note: "来自索引页、做法页和甜点页的正式记录"
    },
    {
      label: "待办项",
      value: overview?.backlog_count ?? 0,
      note: "来源于“再挑战及待记录”工作表"
    },
    {
      label: "专题库",
      value: overview?.library_section_count ?? 0,
      note: "顶层专题维度，例如牛肉、海鲜、早餐等"
    }
  ];

  return (
    <section className="panel overview-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">System overview</p>
          <h2>工作簿驱动的本地菜谱库</h2>
        </div>
      </div>

      <div className="overview-grid">
        {cards.map((card) => (
          <article key={card.label} className="overview-card">
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <p>{card.note}</p>
          </article>
        ))}
      </div>

      <div className="timeline-card">
        <div>
          <span className="eyebrow">最近更新</span>
          <h3>{overview?.latest_recipe_name ?? "尚未导入真实菜谱"}</h3>
        </div>
        <p>{overview?.latest_updated_at ?? "导入后这里会显示最近一次更新的记录。"}</p>
      </div>

      <div className="callout-card">
        <h3>当前设计原则</h3>
        <p>界面围绕真实工作簿的信息结构展示：专题库、分组、菜系、食材、做法和待办状态都会直接入库并参与检索。</p>
      </div>
    </section>
  );
}

export default function App() {
  const [selectedSection, setSelectedSection] = useState("overview");
  const [health, setHealth] = useState(null);
  const [overview, setOverview] = useState(null);
  const [recipes, setRecipes] = useState([]);
  const [filterOptions, setFilterOptions] = useState({
    statuses: [],
    library_sections: [],
    section_names: [],
    cuisines: [],
    ingredients: [],
    tags: [],
    managed_tags: [],
    section_names_by_library_section: {},
    library_sections_by_section_name: {}
  });
  const [search, setSearch] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [selectedLibrarySection, setSelectedLibrarySection] = useState("");
  const [selectedSectionName, setSelectedSectionName] = useState("");
  const [selectedCuisine, setSelectedCuisine] = useState("");
  const [selectedIngredient, setSelectedIngredient] = useState("");
  const [selectedManagedTags, setSelectedManagedTags] = useState([]);
  const [bmdOnly, setBmdOnly] = useState(false);
  const [ccOnly, setCcOnly] = useState(false);
  const [selectedRecipeId, setSelectedRecipeId] = useState(null);
  const [selectedRecipe, setSelectedRecipe] = useState(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);

  const deferredSearch = useDeferredValue(search);
  const allowedSectionNames = selectedLibrarySection
    ? filterOptions.section_names_by_library_section[selectedLibrarySection] ?? []
    : filterOptions.section_names;
  const allowedLibrarySections = selectedSectionName
    ? filterOptions.library_sections_by_section_name[selectedSectionName] ?? []
    : filterOptions.library_sections;
  const visibleSectionNames = selectedLibrarySection
    ? intersectOptions(filterOptions.section_names, allowedSectionNames)
    : selectedSectionName
      ? intersectOptions(filterOptions.section_names, allowedSectionNames)
      : filterOptions.section_names;
  const visibleLibrarySections = selectedSectionName
    ? intersectOptions(filterOptions.library_sections, allowedLibrarySections)
    : selectedLibrarySection
      ? intersectOptions(filterOptions.library_sections, allowedLibrarySections)
      : filterOptions.library_sections;

  useEffect(() => {
    let active = true;

    async function loadShellData() {
      try {
        const [healthData, overviewData, filterData] = await Promise.all([
          fetchHealth(),
          fetchOverview(),
          fetchRecipeFilters()
        ]);
        if (!active) {
          return;
        }

        setHealth(healthData);
        setOverview(overviewData);
        setFilterOptions(filterData);
      } catch (requestError) {
        if (active) {
          setError(requestError.message);
        }
      }
    }

    loadShellData();

    return () => {
      active = false;
    };
  }, [reloadToken]);

  useEffect(() => {
    if (
      selectedLibrarySection &&
      selectedSectionName &&
      !(filterOptions.section_names_by_library_section[selectedLibrarySection] ?? []).includes(selectedSectionName)
    ) {
      setSelectedSectionName("");
    }
  }, [filterOptions.section_names_by_library_section, selectedLibrarySection, selectedSectionName]);

  useEffect(() => {
    if (
      selectedSectionName &&
      selectedLibrarySection &&
      !(filterOptions.library_sections_by_section_name[selectedSectionName] ?? []).includes(selectedLibrarySection)
    ) {
      setSelectedLibrarySection("");
    }
  }, [filterOptions.library_sections_by_section_name, selectedLibrarySection, selectedSectionName]);

  useEffect(() => {
    let active = true;

    async function loadRecipeList() {
      setListLoading(true);

      try {
        const recipeData = await fetchRecipes({
          search: deferredSearch,
          status: selectedStatus,
          librarySection: selectedLibrarySection,
          sectionName: selectedSectionName,
          cuisine: selectedCuisine,
          ingredient: selectedIngredient,
          managedTags: selectedManagedTags,
          bmdOnly,
          ccOnly
        });
        if (!active) {
          return;
        }

        setRecipes(recipeData.items);

        startTransition(() => {
          if (recipeData.items.length === 0) {
            setSelectedRecipeId(null);
            setSelectedRecipe(null);
            return;
          }

          setSelectedRecipeId((currentRecipeId) => {
            const stillVisible = recipeData.items.some((item) => item.id === currentRecipeId);
            return stillVisible ? currentRecipeId : recipeData.items[0].id;
          });
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

    loadRecipeList();

    return () => {
      active = false;
    };
  }, [deferredSearch, selectedStatus, selectedLibrarySection, selectedSectionName, selectedCuisine, selectedIngredient, selectedManagedTags, bmdOnly, ccOnly, reloadToken]);

  useEffect(() => {
    let active = true;

    async function loadRecipeDetail() {
      if (!selectedRecipeId) {
        setSelectedRecipe(null);
        return;
      }

      setDetailLoading(true);

      try {
        const recipeData = await fetchRecipe(selectedRecipeId);
        if (active) {
          setSelectedRecipe(recipeData);
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

    loadRecipeDetail();

    return () => {
      active = false;
    };
  }, [selectedRecipeId]);

  return (
    <div className="app-shell">
      <Sidebar
        health={health}
        overview={overview}
        selectedSection={selectedSection}
        onSelectSection={setSelectedSection}
      />

      <main className="workspace">
        {error ? <div className="error-banner">{error}</div> : null}

        {selectedSection === "overview" ? <OverviewSection overview={overview} /> : null}

        {selectedSection === "recipes" ? (
          <div className="content-grid">
            <RecipeList
              recipes={recipes}
              search={search}
              status={selectedStatus}
              librarySection={selectedLibrarySection}
              sectionName={selectedSectionName}
              cuisine={selectedCuisine}
              ingredient={selectedIngredient}
              managedTags={selectedManagedTags}
              bmdOnly={bmdOnly}
              ccOnly={ccOnly}
              filterOptions={{
                ...filterOptions,
                library_sections: visibleLibrarySections,
                section_names: visibleSectionNames
              }}
              onSearchChange={setSearch}
              onStatusChange={setSelectedStatus}
              onLibrarySectionChange={(value) => {
                setSelectedLibrarySection(value);
                if (value && selectedSectionName) {
                  const allowed = filterOptions.section_names_by_library_section[value] ?? [];
                  if (!allowed.includes(selectedSectionName)) {
                    setSelectedSectionName("");
                  }
                }
              }}
              onSectionNameChange={(value) => {
                setSelectedSectionName(value);
                if (value && selectedLibrarySection) {
                  const allowed = filterOptions.library_sections_by_section_name[value] ?? [];
                  if (!allowed.includes(selectedLibrarySection)) {
                    setSelectedLibrarySection("");
                  }
                }
              }}
              onCuisineChange={setSelectedCuisine}
              onIngredientChange={setSelectedIngredient}
              onManagedTagsChange={setSelectedManagedTags}
              onBmdOnlyChange={setBmdOnly}
              onCcOnlyChange={setCcOnly}
              onResetFilters={() => {
                setSelectedStatus("");
                setSelectedLibrarySection("");
                setSelectedSectionName("");
                setSelectedCuisine("");
                setSelectedIngredient("");
                setSelectedManagedTags([]);
                setBmdOnly(false);
                setCcOnly(false);
                setSearch("");
              }}
              onSelectRecipe={setSelectedRecipeId}
              selectedRecipeId={selectedRecipeId}
              loading={listLoading}
            />
            <RecipeDetail recipe={selectedRecipe} loading={detailLoading} />
          </div>
        ) : null}

        {selectedSection === "imports" ? (
          <div className="section-stack">
            <ImportWorkspace
              onImportCommitted={() => {
                setReloadToken((current) => current + 1);
              }}
            />
            <ImportRefinementPanel />
            <ImportHistory reloadToken={reloadToken} />
          </div>
        ) : null}

        {selectedSection === "pairing" ? <PairingReview reloadToken={reloadToken} /> : null}

        {selectedSection === "refineReview" ? <RefineReview /> : null}

        {selectedSection === "database" ? <DatabaseBrowser /> : null}

        {selectedSection === "aiLogs" ? <AiLogViewer /> : null}

        {selectedSection === "analytics" ? <AnalyticsDashboard reloadToken={reloadToken} /> : null}

        {selectedSection === "tagging" ? (
          <TagManagement
            onOpenRecipe={(recipeId) => {
              setSelectedRecipeId(recipeId);
              setSelectedSection("recipes");
            }}
          />
        ) : null}

        {selectedSection === "ai" ? (
          <AITools
            selectedRecipe={selectedRecipe}
            selectedRecipeId={selectedRecipeId}
            onOpenRecipe={(recipeId) => {
              setSelectedRecipeId(recipeId);
              setSelectedSection("recipes");
            }}
          />
        ) : null}
      </main>
    </div>
  );
}
