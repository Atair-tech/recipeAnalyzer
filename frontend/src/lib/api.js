const isTauriRuntime =
  typeof window !== "undefined" &&
  (window.__TAURI_INTERNALS__ ||
    window.location.protocol === "tauri:" ||
    window.location.hostname === "tauri.localhost");

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (isTauriRuntime ? "http://127.0.0.1:8000/api" : "/api");
const STARTUP_RETRY_ATTEMPTS = isTauriRuntime ? 20 : 1;
const STARTUP_RETRY_DELAY_MS = 500;

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function fetchWithStartupRetry(url, options) {
  let lastError = null;

  for (let attempt = 1; attempt <= STARTUP_RETRY_ATTEMPTS; attempt += 1) {
    try {
      return await fetch(url, options);
    } catch (error) {
      lastError = error;
      if (attempt === STARTUP_RETRY_ATTEMPTS) {
        break;
      }
      await delay(STARTUP_RETRY_DELAY_MS);
    }
  }

  throw lastError;
}

async function request(path, options = {}) {
  const response = await fetchWithStartupRetry(`${API_BASE_URL}${path}`, options);

  if (!response.ok) {
    let detail = "";
    try {
      const errorBody = await response.json();
      detail = errorBody.detail || errorBody.message || "";
    } catch {
      detail = await response.text().catch(() => "");
    }
    throw new Error(detail ? `Request failed: ${response.status} - ${detail}` : `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function buildApiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

async function download(path, fallbackFileName) {
  const fileName = fallbackFileName;
  const link = document.createElement("a");
  link.href = buildApiUrl(path);
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  return { fileName };
}

export function fetchHealth() {
  return request("/health");
}

export function fetchDeepseekApiKeyStatus() {
  return request("/settings/deepseek-api-key");
}

export function saveDeepseekApiKey(apiKey) {
  return request("/settings/deepseek-api-key", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ api_key: apiKey })
  });
}

export function fetchOverview() {
  return request("/overview");
}

export function fetchBirthdaySurpriseEvent() {
  return request("/birthday-surprise/event");
}

export function acknowledgeBirthdaySurpriseEvent(eventId) {
  return request("/birthday-surprise/event/ack", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ event_id: eventId })
  });
}

export function fetchDatabaseTables() {
  return request("/database/tables");
}

export function exportDatabase() {
  if (isTauriRuntime) {
    return request("/database/export-to-downloads", {
      method: "POST"
    });
  }
  return download("/database/export", "recipe_analyzer_backup.db");
}

export function importDatabase(file) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/database/import", {
    method: "POST",
    body: formData
  });
}

export function fetchDatabaseTableRows(tableName, { limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset)
  });
  return request(`/database/tables/${encodeURIComponent(tableName)}?${params.toString()}`);
}

export function fetchAnalyticsSummary({ dimension = "library_section", scope = "all", topN = 12 } = {}) {
  const params = new URLSearchParams({
    dimension,
    scope,
    top_n: String(topN)
  });
  return request(`/analytics/summary?${params.toString()}`);
}

export function fetchNaturalSearch(query, { limit = 10, offset = 0 } = {}) {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    offset: String(offset)
  });
  return request(`/ai/natural-search?${params.toString()}`);
}

export function exportNaturalSearch(query) {
  const params = new URLSearchParams({ q: query });
  return download(`/ai/natural-search/export?${params.toString()}`, "natural_search_results.xlsx");
}

export function fetchTagSuggestions(recipeId, limit = 8) {
  const params = new URLSearchParams({ limit: String(limit) });
  return request(`/ai/recipes/${recipeId}/tag-suggestions?${params.toString()}`);
}

export function fetchLlmStatus() {
  return request("/ai/llm/status");
}

export function fetchLlmModels() {
  return request("/ai/llm/models");
}

export function askLlm(payload) {
  return request("/ai/llm/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function askLlmStream(payload, { onEvent, signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/ai/llm/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    signal
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Streaming response is not available");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let finalResult = null;

  function handleLine(line) {
    if (!line.trim()) {
      return;
    }
    const event = JSON.parse(line);
    if (onEvent) {
      onEvent(event);
    }
    if (event.type === "error") {
      throw new Error(event.error || "Streaming request failed");
    }
    if (event.type === "final") {
      finalResult = event.result;
    }
  }

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      handleLine(line);
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    handleLine(buffer);
  }

  if (!finalResult) {
    throw new Error("Streaming completed without a final result");
  }

  return finalResult;
}

export function fetchAiLogs({ limit = 50, offset = 0, feature = "", status = "" } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset)
  });
  if (feature) {
    params.set("feature", feature);
  }
  if (status) {
    params.set("status", status);
  }
  return request(`/ai/logs?${params.toString()}`);
}

export function fetchAiLogDetail(logId) {
  return request(`/ai/logs/${logId}`);
}

export function fetchManagedTags() {
  return request("/tagging/tags");
}

export function createManagedTag(payload) {
  return request("/tagging/tags", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export function updateManagedTag(tagId, payload) {
  return request(`/tagging/tags/${tagId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export function deleteManagedTag(tagId) {
  return request(`/tagging/tags/${tagId}`, {
    method: "DELETE"
  });
}

export function fetchManagedTagRecipes(tagId, { search = "", limit = 100 } = {}) {
  const params = new URLSearchParams({
    limit: String(limit)
  });
  if (search) {
    params.set("search", search);
  }
  return request(`/tagging/tags/${tagId}/recipes?${params.toString()}`);
}

export function deleteManagedTagRecipe(tagId, recipeId) {
  return request(`/tagging/tags/${tagId}/recipes/${recipeId}`, {
    method: "DELETE"
  });
}

export function fetchTaggingStatus() {
  return request("/tagging/status");
}

export function startTaggingRun(model) {
  return request("/tagging/run/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ model })
  });
}

export function pauseTaggingRun() {
  return request("/tagging/run/pause", {
    method: "POST"
  });
}

export function resumeTaggingRun() {
  return request("/tagging/run/resume", {
    method: "POST"
  });
}

export function fetchRefineReviewItems({ search = "", status = "all", issueType = "", limit = 200 } = {}) {
  const params = new URLSearchParams({
    status,
    limit: String(limit)
  });
  if (search) {
    params.set("search", search);
  }
  if (issueType) {
    params.set("issue_type", issueType);
  }
  return request(`/imports/refine/review?${params.toString()}`);
}

export function fetchRefineReviewDetail(recipeId) {
  return request(`/imports/refine/review/${recipeId}`);
}

export function updateRefineReview(recipeId, payload) {
  return request(`/imports/refine/review/${recipeId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export function rerunRefineReview(recipeId, model) {
  return request(`/imports/refine/review/${recipeId}/rerun`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ model })
  });
}

export function fetchRecipes({
  search = "",
  status = "",
  librarySection = "",
  sectionName = "",
  cuisine = "",
  ingredient = "",
  managedTags = [],
  bmdOnly = false,
  ccOnly = false
} = {}) {
  const params = new URLSearchParams();

  if (search) {
    params.set("search", search);
  }
  if (status) {
    params.set("status", status);
  }
  if (librarySection) {
    params.set("library_section", librarySection);
  }
  if (sectionName) {
    params.set("section_name", sectionName);
  }
  if (cuisine) {
    params.set("cuisine", cuisine);
  }
  if (ingredient) {
    params.set("ingredient", ingredient);
  }
  for (const managedTag of managedTags) {
    if (managedTag) {
      params.append("managed_tag", managedTag);
    }
  }
  if (bmdOnly) {
    params.set("bmd_only", "true");
  }
  if (ccOnly) {
    params.set("cc_only", "true");
  }

  const query = params.toString();
  return request(`/recipes${query ? `?${query}` : ""}`);
}

export function exportRecipes(filters = {}) {
  const params = new URLSearchParams();
  if (filters.search) {
    params.set("search", filters.search);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  if (filters.librarySection) {
    params.set("library_section", filters.librarySection);
  }
  if (filters.sectionName) {
    params.set("section_name", filters.sectionName);
  }
  if (filters.cuisine) {
    params.set("cuisine", filters.cuisine);
  }
  if (filters.ingredient) {
    params.set("ingredient", filters.ingredient);
  }
  for (const managedTag of filters.managedTags || []) {
    if (managedTag) {
      params.append("managed_tag", managedTag);
    }
  }
  if (filters.bmdOnly) {
    params.set("bmd_only", "true");
  }
  if (filters.ccOnly) {
    params.set("cc_only", "true");
  }
  return download(`/recipes/export?${params.toString()}`, "recipes_export.xlsx");
}

export function fetchRecipe(recipeId) {
  return request(`/recipes/${recipeId}`);
}

export function fetchRecipeFilters() {
  return request("/recipes/filters");
}

export function fetchRecipeEditorSchema() {
  return request("/recipes/editor/schema");
}

export function fetchRecipeEditorTables() {
  return request("/recipes/editor/tables");
}

export function fetchRecipeEditorUserViews() {
  return request("/recipes/editor/user-views");
}

export function fetchRecipeEditorTableRows({ table, filters = {}, limit = 100, offset = 0 }) {
  return request("/recipes/editor/table-rows", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ table, filters, limit, offset })
  });
}

export function fetchRecipeEditorUserViewRows({ view, filters = {}, limit = 100, offset = 0, sortColumn = "", sortDirection = "" }) {
  return request("/recipes/editor/user-view-rows", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      view,
      filters,
      limit,
      offset,
      sort_column: sortColumn || null,
      sort_direction: sortDirection || null
    })
  });
}

export function fetchRecipeEditorUserViewFilterValues({ view, column, filters = {}, search = "", limit = 5000 }) {
  return request("/recipes/editor/user-view-filter-values", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ view, column, filters, search, limit })
  });
}

export function executeRecipeEditorSql(sql) {
  return request("/recipes/editor/sql", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ sql })
  });
}

export function applyRecipeEditorTableChanges({ table, changes }) {
  return request("/recipes/editor/apply", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ table, changes })
  });
}

export function fetchRecipeEditorRows() {
  return request("/recipes/editor/rows");
}

export function createRecipeEditorRow(values) {
  return request("/recipes/editor/rows", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ values })
  });
}

export function updateRecipeEditorRow(recipeId, values) {
  return request(`/recipes/editor/rows/${recipeId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ values })
  });
}

function buildImportFormData(file, mapping = null) {
  const formData = new FormData();
  formData.append("file", file);
  if (mapping) {
    formData.append("mapping_json", JSON.stringify(mapping));
  }
  return formData;
}

export function previewImport(file, mapping = null) {
  const formData = buildImportFormData(file, mapping);
  return request("/imports/preview", {
    method: "POST",
    body: formData
  });
}

export function commitImport(file, mapping = null) {
  const formData = buildImportFormData(file, mapping);
  return request("/imports/commit", {
    method: "POST",
    body: formData
  });
}

export function fetchImportBatches(limit = 20) {
  const params = new URLSearchParams({ limit: String(limit) });
  return request(`/imports/batches?${params.toString()}`);
}

export function fetchImportBatchDetail(batchId, rowLimit = 20) {
  const params = new URLSearchParams({ row_limit: String(rowLimit) });
  return request(`/imports/batches/${batchId}?${params.toString()}`);
}

export function fetchImportRefineStatus() {
  return request("/imports/refine/status");
}

export function startImportRefineRun(model) {
  return request("/imports/refine/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ model })
  });
}

export function pauseImportRefineRun() {
  return request("/imports/refine/pause", {
    method: "POST"
  });
}

export function resumeImportRefineRun() {
  return request("/imports/refine/resume", {
    method: "POST"
  });
}

export function fetchIngredientFilterStatus() {
  return request("/imports/ingredient-filter/status");
}

export function startIngredientFilterRun(model, provider = "deepseek_api") {
  return request("/imports/ingredient-filter/start", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ model, provider })
  });
}

export function pauseIngredientFilterRun() {
  return request("/imports/ingredient-filter/pause", {
    method: "POST"
  });
}

export function resumeIngredientFilterRun() {
  return request("/imports/ingredient-filter/resume", {
    method: "POST"
  });
}

export function fetchPairingReview() {
  return request("/pairing/review");
}

export function createPairOverride(payload) {
  return request("/pairing/overrides", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export function createPairOverridesBulk(items) {
  return request("/pairing/overrides/bulk", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ items })
  });
}

export function deletePairOverride(overrideId) {
  return request(`/pairing/overrides/${overrideId}`, {
    method: "DELETE"
  });
}
