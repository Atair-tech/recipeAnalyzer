import { startTransition, useDeferredValue, useEffect, useState } from "react";

import AnalyticsDashboard from "./components/AnalyticsDashboard";
import AiLogViewer from "./components/AiLogViewer";
import AITools from "./components/AITools";
import BirthdaySurprise from "./components/BirthdaySurprise";
import DatabaseBrowser from "./components/DatabaseBrowser";
import ImportHistory from "./components/ImportHistory";
import ImportRefinementPanel from "./components/ImportRefinementPanel";
import ImportWorkspace from "./components/ImportWorkspace";
import PairingReview from "./components/PairingReview";
import RefineReview from "./components/RefineReview";
import RecipeDetail from "./components/RecipeDetail";
import RecipeEditor from "./components/RecipeEditor";
import RecipeList from "./components/RecipeList";
import Sidebar from "./components/Sidebar";
import TagManagement from "./components/TagManagement";
import {
  acknowledgeBirthdaySurpriseEvent,
  fetchBirthdaySurpriseEvent,
  fetchHealth,
  fetchOverview,
  fetchRecipe,
  fetchRecipeFilters,
  fetchRecipes
} from "./lib/api";

function intersectOptions(primaryOptions, allowedOptions) {
  if (!allowedOptions || allowedOptions.length === 0) {
    return [];
  }
  const allowedSet = new Set(allowedOptions);
  return primaryOptions.filter((option) => allowedSet.has(option));
}

function StartupGate({ open, onOpen, onDisable }) {
  return (
    <div className={`startup-gate ${open ? "open" : ""}`} aria-hidden={open ? "true" : "false"}>
      <button type="button" className="startup-gate-core" onClick={onOpen}>
        <img className="startup-gate-image" src="/resource/birthday-table.png" alt="" />
      </button>
      <button type="button" className="startup-gate-skip" onClick={onDisable}>
        以后不再显示
      </button>
    </div>
  );
}

export default function App() {
  const [routeHash, setRouteHash] = useState(() => window.location.hash);
  const [showStartupGate, setShowStartupGate] = useState(() => {
    try {
      return window.localStorage.getItem("recipeAnalyzer.startupGateDisabled") !== "1";
    } catch {
      return true;
    }
  });
  const [startupGateOpen, setStartupGateOpen] = useState(false);
  const [selectedSection, setSelectedSection] = useState("analytics");
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

  useEffect(() => {
    function handleHashChange() {
      setRouteHash(window.location.hash);
    }
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    if (routeHash === "#birthday") {
      return;
    }
    try {
      if (window.sessionStorage.getItem("recipeAnalyzer.forceStartupGate") === "1") {
        window.sessionStorage.removeItem("recipeAnalyzer.forceStartupGate");
        setStartupGateOpen(false);
        setShowStartupGate(true);
      }
    } catch {
      // Ignore storage failures; normal startup behavior still works.
    }
  }, [routeHash]);

  useEffect(() => {
    let active = true;
    let timerId = null;

    async function checkBirthdayEvent() {
      try {
        const event = await fetchBirthdaySurpriseEvent();
        if (!active) {
          return;
        }
        if (event.pending && event.route === "birthday" && event.event_id) {
          window.location.hash = "birthday";
          acknowledgeBirthdaySurpriseEvent(event.event_id).catch(() => {});
        }
      } catch {
        // The desktop backend may still be starting; the next poll will retry.
      } finally {
        if (active) {
          timerId = window.setTimeout(checkBirthdayEvent, 2000);
        }
      }
    }

    checkBirthdayEvent();

    return () => {
      active = false;
      if (timerId) {
        window.clearTimeout(timerId);
      }
    };
  }, []);

  const startupGateVisible = showStartupGate && routeHash !== "#birthday";

  function openStartupGate({ disableFuture = false } = {}) {
    if (startupGateOpen) {
      return;
    }
    if (disableFuture) {
      try {
        window.localStorage.setItem("recipeAnalyzer.startupGateDisabled", "1");
      } catch {
        // Ignore storage failures; the gate still opens normally.
      }
    }
    setStartupGateOpen(true);
    window.setTimeout(() => setShowStartupGate(false), 420);
  }

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

  if (routeHash === "#editor") {
    return <RecipeEditor />;
  }

  if (routeHash === "#birthday") {
    return <BirthdaySurprise />;
  }

  return (
    <div className="app-shell">
      {startupGateVisible ? (
        <StartupGate
          open={startupGateOpen}
          onOpen={() => openStartupGate()}
          onDisable={() => openStartupGate({ disableFuture: true })}
        />
      ) : null}

      <Sidebar
        health={health}
        overview={overview}
        selectedSection={selectedSection}
        onSelectSection={setSelectedSection}
      />

      <main className="workspace">
        {error ? <div className="error-banner">{error}</div> : null}


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
            <ImportHistory reloadToken={reloadToken} />
          </div>
        ) : null}

        {selectedSection === "ingredientAnalysis" ? <ImportRefinementPanel /> : null}

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

        <div className={selectedSection === "ai" ? "preserved-section" : "preserved-section preserved-section-hidden"}>
          <AITools
            onOpenRecipe={(recipeId) => {
              setSelectedRecipeId(recipeId);
              setSelectedSection("recipes");
            }}
          />
        </div>
      </main>
    </div>
  );
}
