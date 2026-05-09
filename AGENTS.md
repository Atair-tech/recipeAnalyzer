# AGENTS.md

This repository is worked on by Codex agents. Before making changes, read this file and then read `codex-handoff.md` in the repository root.

`codex-handoff.md` contains the current project state, recent decisions, known issues, packaging notes, and the next recommended debugging steps. It should be updated whenever a session ends with meaningful unresolved context.

## Project Summary

Recipe Analyzer is a local-first recipe library built around a real Excel workbook. Excel remains the source of truth; SQLite is the application's working database. AI-generated data is only reference material and must not overwrite or reinterpret the original Excel text in the record detail page.

## Development Commands

Backend:

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
Set-Location .\frontend
npm run dev
```

Frontend build:

```powershell
npm --prefix frontend run build
```

Desktop package:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

The NSIS installer is generated at the current app version under:

```text
src-tauri\target\release\bundle\nsis\Recipe Analyzer_<version>_x64-setup.exe
```

## Architecture

- Frontend: React + Vite in `frontend/`.
- Backend: FastAPI in `backend/app/`.
- Database: SQLite.
- Desktop wrapper: Tauri v2 in `src-tauri/`.
- Desktop backend sidecar: PyInstaller-built executable from `desktop/tauri_backend/recipe_backend_sidecar.py`.
- Independent helper tools:
  - `desktop/db_refiner/` for ingredient refinement.
  - `desktop/db_tagger/` for automatic tagging.

## Working Rules

- Do not replace or alter original Excel-derived recipe text as part of AI refinement. The original ingredients, seasonings, and steps shown in record detail must remain authoritative.
- AI-generated standardized ingredients and automatic tags must be labeled as reference-only.
- Preserve incremental behavior: imports, refinement, and tagging should skip unchanged successful records unless quality audit flags them.
- Pairing review depends on the current source workbook at `DATA_DIR\recipes.xlsx`; desktop packaging must bundle `data\recipes.xlsx`, and committed Excel imports should keep that workbook in sync.
- Be careful with encoding. Source files are UTF-8 and contain Chinese UI strings.
- Use `apply_patch` for edits.
- Do not revert unrelated user changes. The working tree is expected to be dirty.
- For frontend work, run `npm --prefix frontend run build`.
- For backend Python changes, run `.\.venv\Scripts\python.exe -m py_compile <file>` or targeted tests/scripts.
- For desktop packaging changes, run `npm run desktop:build`.

## Tauri/Rust Notes

Rust was installed with the TUNA mirror because normal rustup downloads may stall in China:

```powershell
[Environment]::SetEnvironmentVariable("RUSTUP_DIST_SERVER", "https://mirrors.tuna.tsinghua.edu.cn/rustup", "User")
[Environment]::SetEnvironmentVariable("RUSTUP_UPDATE_ROOT", "https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup", "User")
```

In the current shell, prepend cargo if needed:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
```

## Packaging Notes

The backend sidecar is built with `--noconsole`. In that mode, `sys.stdout` and `sys.stderr` can be `None`, so `recipe_backend_sidecar.py` must keep explicit stdio/log handling. It writes logs to:

```text
%LOCALAPPDATA%\RecipeAnalyzer\logs\backend.log
```

The sidecar build uses `desktop/tauri_backend/build_sidecar.py` to monkey-patch optional PyInstaller PE timestamp/checksum rewrites. This is intentional: on the current Windows machine, security tooling can lock the generated executable during those optional post-processing steps.

## Handoff

Always read `codex-handoff.md` for the latest state before starting work. If you make meaningful progress, update `codex-handoff.md` before ending the session.
