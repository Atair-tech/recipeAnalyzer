# Architecture

## Chosen path

This repository follows the browser-first path:

1. React frontend in the browser
2. FastAPI backend on localhost
3. SQLite as the local source of truth
4. Tauri added later as a shell around the frontend

This keeps the expensive part of the work where it belongs:

- Excel parsing and normalization in Python
- persistent local data in SQLite
- search, list, detail, and future AI services behind API boundaries

## Folder design

```text
backend/
  app/
    api/
      routes/
    core/
    db/
    services/
desktop/
  README.md
frontend/
  src/
    components/
    lib/
data/
```

## Responsibility split

### `frontend/`

- render the knowledge-base style UI
- call backend APIs
- host search, list, detail, and import interactions

### `backend/`

- initialize SQLite
- own schema and data access
- parse Excel in later milestones
- expose API routes for the frontend

### `desktop/`

- reserved for future Tauri integration
- should only package the frontend and orchestrate the local backend
- should not absorb domain logic

## Tauri migration path

When the browser-first MVP is stable, add Tauri with this rule:

- keep `frontend/` as the UI
- keep `backend/` as the data and service layer
- put Tauri-specific windowing, file dialogs, and packaging code in `desktop/`

That keeps the product modular:

- browser mode for development
- desktop mode for end-user delivery

## Database approach

SQLite is the canonical store. Excel is import input only.

The schema already reserves:

- recipe records
- ingredients and recipe-ingredient links
- tags and recipe-tag links
- import batches
- raw imported rows for traceability

This is the correct tradeoff for the stated requirement that raw input must remain recoverable.
