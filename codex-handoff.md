# Codex Handoff

Last updated: 2026-05-06

## Current Status

The project has a working web app and a Tauri desktop packaging path. The latest major focus was packaging the app into a Windows installer and debugging why the installed version on another computer exits immediately.

Current local web dev services were started for inspection on 2026-05-06:

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8000
Logs:     logs\web-backend.*.log and logs\web-frontend.*.log
```

If those ports are busy in a future session, inspect/stop the existing processes before starting new ones.

The latest installer was rebuilt at:

```text
D:\ML_DA\recipeAnalyzer\src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.0_x64-setup.exe
```

Superseded by the latest upgrade build:

```text
D:\ML_DA\recipeAnalyzer\src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.1_x64-setup.exe
```

The latest target-machine screenshot showed the Tauri app starting, but backend startup failed with:

```text
[backend] failed to spawn sidecar: 系统找不到指定的路径。 (os error 3)
```

Root cause found locally: Tauri bundled the sidecar as `recipe-backend.exe` next to `recipe-analyzer.exe`, but `src-tauri/src/lib.rs` was trying to spawn `binaries/recipe-backend`, which resolves to a non-existent `binaries\recipe-backend.exe` under the installed app directory. This has been fixed and the installer has been rebuilt.

The next screenshot showed the sidecar now starts and reaches `Starting uvicorn on 127.0.0.1:8000`, but the frontend still showed `Failed to fetch`. Two fixes were added:

- bundle the seed SQLite database into the installer;
- retry frontend API requests during Tauri backend cold start.

Latest follow-up: the target machine only has `qwen3.5:4b` and `qwen3:4b`, but the AI panel showed `qwen3:0.6b`. Root cause was the hardcoded backend fallback model and the frontend adding `status.default_model` to the model dropdown even when it was not installed. This has been fixed and the installer rebuilt again.

Latest installer/update follow-up: users do not need to manually uninstall before installing a newer build, but each installer must have a higher app version. The app was bumped from `0.1.0` to `0.1.1`, then to `0.1.2` for the Ollama reconnect UI fix, then to `0.1.3` for the model process display fix, then to `0.1.4` for Ollama thinking suppression, then to `0.1.5` for backend process cleanup, then to `0.1.6` for desktop database export, then to `0.1.7` for ingredient filter search, then to `0.1.8` for robust automatic tag parsing, then to `0.1.9` for showing all matching ingredients in the ingredient filter, then to `0.1.10` for removing current-recipe context from AI chat and compacting the recipe-library filter layout, then to `0.1.11` for preserving AI ingredient analysis across Excel imports when ingredient-analysis inputs did not change, then to `0.1.12` for startup gate behavior, then to `0.1.13` for desktop pairing review source workbook availability. Future release builds should bump this again. The latest NSIS installer is:

```text
src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.13_x64-setup.exe
```

Latest pairing review follow-up: the Pairing Review page reparses `DATA_DIR\recipes.xlsx`, so it worked in web/dev where `data\recipes.xlsx` existed but could fail in the installed exe because only the seed SQLite DB was bundled/copied. Fix: Tauri now bundles `../data/recipes.xlsx` as `data/recipes.xlsx`; the backend sidecar copies it into `%LOCALAPPDATA%\RecipeAnalyzer\data\recipes.xlsx` when missing; committed Excel imports now persist the uploaded workbook to `DATA_DIR\recipes.xlsx` so future pairing reviews use the latest imported workbook. Build verification confirmed `src-tauri\target\release\data\recipes.xlsx` exists and `Recipe Analyzer_0.1.13_x64-setup.exe` was generated.

Latest web editor follow-up: the user requested a separate in-app recipe editing model so users do not need to return to Excel for routine edits. Default scope for future changes is now web-only unless the user explicitly asks to update the exe. The web app now has an `编辑模式` button on the analytics overview hero. It opens `#editor` in a separate browser page/tab. The editor page uses a spreadsheet-style table with all recipe database fields plus reference-only joined fields for tags, automatic tags, and visible standardized ingredients. It supports live keyword search, default filters for主料/标准食材、大地域、小地域、记录类型、专题库, arbitrary added field filters, keyword-as-filter, and AND/OR composition. Users can edit recipe-table fields, edit manual tags through a comma/顿号 separated text field, save per row, and create new rows. Automatic tags and standardized ingredients remain read-only reference fields. Backend endpoints added under `/api/recipes/editor/*`, and the previously disabled `PUT /api/recipes/{id}` now updates recipe fields. Current implementation edits the SQLite working database only; it does not write changes back to `data\recipes.xlsx`, so a future Excel import may overwrite overlapping recipe fields unless an import/merge policy is added. Follow-up UI change: the editor no longer shows a large "菜谱编辑模式" title or English heading; the top area is compressed into a desktop-spreadsheet-style menu strip, compact toolbar, one-line filter rows, and the table now occupies nearly all of the viewport.

Latest editor UX follow-up: direct editing inside table cells was removed. The spreadsheet table is now read-only for browsing/filtering. Users click `修改` in a row or `新建条目` in the toolbar to open a modal form, edit fields there, then save. This avoids accidental cell edits and reduces table rendering cost.

Latest editor data-quality follow-up: "小地域" maps to `recipes.sub_cuisine`, which historically came from Excel index sheet column F. Some workbook rows used that column for author/account/source IDs rather than geography, causing values like `45662` and `John's Kitchen` to appear as small-region suggestions. `get_recipe_editor_schema()` now uses a fixed region whitelist for `sub_cuisine` options instead of distinct database values. Existing dirty values still remain visible in table/form values until manually cleaned, but they are no longer suggested in the dropdown.

Latest schema cleanup follow-up: the user asked to delete fields without corresponding xlsx columns. Removed these columns from `recipes`: `alias`, `flavor`, `difficulty`, `estimated_time`, `servings`, and `tools`. Updated schema, startup migration, Excel parser payloads, import insert/update SQL, recipe editor schema/list/detail APIs, search index rebuild, and recipe detail UI. `source_text` was kept because it is generated from Excel source content for traceability. A pre-migration backup was created at `data\backups\recipe_analyzer_before_drop_non_xlsx_fields_20260506_151459.db`. Migration ran successfully on `data\recipe_analyzer.db`; `PRAGMA table_info(recipes)` no longer shows the removed columns, and `/api/recipes/editor/schema` now returns 26 fields.

Latest pairing review fix: after the schema cleanup, `/api/pairing/review` failed with `local variable 'payload' referenced before assignment`. Root cause was an accidental indentation error in `_parse_dessert_sheet()` in `workbook_parser.py`; `payload = _base_recipe_payload(...)` was nested under the `if not name: continue` branch. Fixed indentation. Verified `get_pairing_review()` returns 11 sections and 1342 total parsed records; HTTP `/api/pairing/review` returns 200 after backend restart.

Latest birthday surprise follow-up: the user wants a one-off birthday surprise at 2026-05-10 00:00 Asia/Shanghai while the backend continues running after the browser/front-end window is closed. Added `backend/app/services/birthday_surprise_service.py`; backend lifespan starts a daemon scheduler thread. If `data\birthday_surprise_2026.done` does not exist, the thread waits until 2026-05-10 00:00, shows a topmost Tkinter Windows dialog with text `生日快乐！` and button `继续`, writes the done flag, then opens `http://127.0.0.1:5173/#birthday`. Added frontend `BirthdaySurprise` route for `#birthday`: white screen for about 2 seconds, then plays `/resource/birthDayVid.mp4`; after the video ends, clicking the page shows `/resource/birthday-table.png`. Copied assets into `frontend/public/resource/`: `birthDayVid.mp4`, `birthday-table.png`, and `餐桌.png`. Build/compile passed. Current session started backend on 8000 and frontend dev server on 5173 in hidden background processes; both endpoints and asset URLs returned HTTP 200. The done flag currently does not exist.

Latest birthday verification follow-up: rechecked the 2026-05-10 00:00 popup chain on 2026-05-09. Added a status log at `data\birthday_surprise_status.log` and a safer fallback path: if the Tkinter dialog fails, the backend now attempts a Windows native message box, still writes the done flag when possible, and still opens the birthday frontend URL. Fast-forward simulation verified waiting, dialog callback, done-flag write, frontend open, and fallback behavior. Recompiled `birthday_surprise_service.py` and `main.py`; `npm --prefix frontend run build` passed. Restarted the live web backend; `data\birthday_surprise_status.log` now records `scheduler starting; target=2026-05-10T00:00:00+08:00` and `waiting`. Live checks confirmed backend `127.0.0.1:8000`, frontend `127.0.0.1:5173`, video, and image assets all return HTTP 200; `data\birthday_surprise_2026.done` and `data\birthday_surprise_error.log` are absent.

Latest birthday desktop package follow-up: built a special `0.1.14` installer for off-machine testing. Birthday scheduler now has three one-time targets: `2026-05-09 18:45`, `2026-05-09 18:50`, and `2026-05-10 00:00` Asia/Shanghai. The first two write per-target done flags (`birthday_surprise_20260509_1845.done`, `birthday_surprise_20260509_1850.done`); the final midnight target still writes `birthday_surprise_2026.done`. Backend now publishes a pending frontend event to `DATA_DIR\birthday_surprise_event.json`; system APIs expose GET `/api/birthday-surprise/event` and POST `/api/birthday-surprise/event/ack`; the frontend polls these APIs and switches to `#birthday` when an event is pending. The sidecar sets `RECIPE_ANALYZER_DESKTOP_EXE` to the sibling desktop executable, and the birthday backend opens that exe instead of the Vite dev URL when packaged. For this special package, Tauri no longer kills the backend sidecar on window close/app exit so the backend can keep waiting after the frontend window is closed. Verification: Python compile passed, fast-forward scheduler simulation passed including event ack, `npm --prefix frontend run build` passed, and `npm run desktop:build` generated `src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.14_x64-setup.exe` plus MSI.

Latest birthday test correction: user reported the 0.1.14 desktop package did not behave correctly: installing after old test times caused repeated birthday dialogs; the dialog-launched frontend did not play video or bypass the startup gate; and the normal database page became unusable when launched via the dialog path. Fixes in `0.1.15`: missed test triggers now skip after a 20-second grace period, while the real midnight trigger still has the 12-hour catch-up window; backend no longer tries to launch the desktop exe from the dialog flow, it only publishes the pending birthday event and falls back to opening the dev URL for web/dev; frontend bypasses the startup gate on `#birthday`; birthday video is muted + autoplay for more reliable WebView playback. Added fresh test triggers `2026-05-09 19:18` and `2026-05-09 19:22`. Verified Python compile, frontend build, Rust `cargo check`, and `npm run desktop:build`. Latest test installer: `src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.15_x64-setup.exe`.

Latest birthday package correction: user correctly identified that opening `http://127.0.0.1:5173/#birthday` cannot work on another computer without the Vite dev server. In `0.1.16+`, packaged backend restores desktop exe launch using `RECIPE_ANALYZER_DESKTOP_EXE`, while setting `RECIPE_ANALYZER_PRESERVE_BACKEND=1`; both Tauri startup cleanup and `recipe_backend_sidecar.py` honor that flag so the newly opened frontend does not kill the existing backend holding the birthday event. `0.1.17` adds a fresh test trigger at `2026-05-09 20:00` Asia/Shanghai while retaining the real `2026-05-10 00:00` trigger. Verified Python compile, sidecar compile, frontend build, Rust `cargo check`, and `npm run desktop:build`. Latest installer: `src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.17_x64-setup.exe`.

Latest birthday UX correction: after the birthday video, the app should not remain on the final table image. `0.1.20` changes `BirthdaySurprise.jsx` so video end immediately returns to the main app and forces the startup overlay to show. The startup overlay itself now uses `/resource/birthday-table.png` as the full-screen launch image instead of the previous metal-door animation; clicking the image dismisses it and opens the normal app. Verification: frontend build, backend compile, Rust check, and desktop build passed. Latest installer: `src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.20_x64-setup.exe`.

Latest birthday test package: user requested additional test triggers at `2026-05-10 09:30` and `2026-05-10 10:00` Asia/Shanghai. Added trigger IDs `20260510_0930` and `20260510_1000`, bumped app/package/Tauri version to `0.1.21`, verified Python compile, sidecar compile, frontend build, Rust `cargo check`, and desktop build. Latest installer: `src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.21_x64-setup.exe`.

Latest database cleanup follow-up: the user asked to clean `miniappoutput\recipe_analyzer_backup_20260430_133853.db`. The following tables were cleared in that file only: `ai_conversation_logs`, `import_batches`, and `raw_import_rows`; `recipes.last_import_batch_id` was set to `NULL`. Counts after cleanup: `ai_conversation_logs=0`, `import_batches=0`, `raw_import_rows=0`, `recipes=1349`, `recipe_ingredients=11564`, `recipe_managed_tags=3232`. A safety copy was created at:

```text
miniappoutput\recipe_analyzer_backup_20260430_133853_before_clear_logs_imports.db
```

Latest startup gate follow-up: the metallic startup gate now shows on every app launch by default. The old `recipeAnalyzer.startupGateSeen` localStorage flag is ignored. The lower-right button now says `以后不再显示`; clicking it dismisses the current gate and writes `recipeAnalyzer.startupGateDisabled=1`, so future launches skip the gate.

Latest UI follow-up: if the app starts before Ollama, the AI page now shows a `重试连接` button inside the Ollama status pill only when LLM is disconnected. Clicking it re-fetches Ollama status/models and DeepSeek key status, then updates the selected model from the installed model list.

Latest AI chat UI follow-up: raw model thinking output was unreadable and exposed internal reasoning. The streaming chat now shows a concise `处理过程` stage summary instead of raw `thinking_chunk` text, and requests are sent with `show_reasoning: false`.

Latest Ollama behavior follow-up: `qwen3.5:4b` can still emit `ThinkingProcess:` inside normal message content if not explicitly controlled. Backend now sends Ollama top-level `think: false`, adds prompt text to only output the final user-facing answer, and strips thinking-like content from both non-streaming and streaming responses before returning it to the frontend.

Latest desktop process follow-up: closing the Recipe Analyzer window could leave `recipe-backend.exe` processes resident, and repeated open/close cycles could accumulate several. Tauri now kills the managed sidecar on both window close and app `RunEvent::ExitRequested`/`RunEvent::Exit`; it also terminates same-path stale `recipe-backend.exe` processes before starting a new sidecar. The sidecar writes `%LOCALAPPDATA%\RecipeAnalyzer\backend.pid` and terminates the previous same-path PID on startup.

Latest desktop export follow-up: in the exe client, `导出数据库` could show "download started" with no saved file because the WebView download flow for backend file streams is unreliable. In Tauri runtime, export now calls a backend endpoint that copies the SQLite DB directly into the user's Downloads folder and returns the full saved path for the success message.

Latest recipe filter follow-up: the ingredient dropdown in the recipe library was too long. It has been replaced with a searchable ingredient selector that filters client-side and displays all matching ingredients.

Latest AI chat/layout follow-up: the AI chat no longer exposes or sends a `当前菜谱` option. `AITools.jsx` always sends `selected_recipe_id: null`, `App.jsx` no longer passes the selected recipe into AI chat, and the backend route/service defensively ignores any `selected_recipe_id` sent by older clients. The recipe library filter area was compacted by moving keyword search into the filter card's primary row, placing automatic tags plus BMD/CC into a compact secondary row, reducing filter control padding, and letting the recipe list flex to fill the available vertical space.

Latest import/refine incremental follow-up: after completing AI ingredient analysis and tagging, importing a lightly changed Excel workbook could make Step1 run all 1300+ recipes again. Root causes: Step1 compared the current code's `refine_version` against older successful v6 hashes, and Excel import treated full-record `source_hash` changes as ingredient changes, calling `sync_recipe_ingredients()` and overwriting AI-refined `recipe_ingredients` even when only non-Step1 fields changed. Fix: added `refine_hash_service.py` with a dedicated ingredient-analysis input hash based on `name`, `library_section`, `section_name`, `ingredients_text`, and `seasonings_text`; import now only resets `recipe_ingredients` when those inputs change, otherwise it preserves existing AI results and migrates successful refine state to the dedicated hash. Step1 now stores/compares this dedicated hash and treats known v6 successful refine hashes as compatible.

Latest automatic tagging follow-up: backup database `miniappoutput\recipe_analyzer_backup_20260430_083641.db` showed run 3 with model `qwen3.5:4b`, `processed_count=1321`, `tagged_count=11`, `error_count=1310`. Ollama calls succeeded, but most responses used a string array shape such as `{"tags":["焖炖","下饭","高蛋白"]}`. The parser expected objects and failed with `'str' object has no attribute 'get'`. `managed_tag_service.py` now accepts both object tags and string tags, and `TAG_PROMPT_VERSION` was bumped so rerunning the tag job reprocesses previous false successes too.

Latest tagging quality analysis: backup database `miniappoutput\recipe_analyzer_backup_20260430_110023.db` completed run 4 with model `qwen3.5:4b`, `processed_count=1321`, `tagged_count=1321`, `error_count=0`. Final assignments: 3219 tag rows, 1267 recipes with tags, 54 without tags. Tags per recipe: 0 tags = 54, 1 tag = 140, 2 tags = 302, 3 tags = 825. Raw model responses were mostly string arrays (`1311/1321`), so current `reason` values are generic (`模型直接返回标签名。`) and confidence values are parser-estimated (`0.72-0.78`), not model-provided. Main quality concern: high-frequency broad tags (`高蛋白` 709, `低门槛` 576, `酱香` 379, `下饭` 291) are useful for coarse filtering but not fully reliable; `低门槛` appears over-applied, while `酱香` and `蒜香` have some weak matches. Some intended tags are never used (`一锅出`, `宴客`, `便当友好`, `进阶操作`), likely due conservative post-filtering and model output shape.

## Most Recent Changes

### Backend sidecar logging

File:

```text
desktop/tauri_backend/recipe_backend_sidecar.py
```

Changes:

- Handles `sys.stdout` and `sys.stderr` being `None` under PyInstaller `--noconsole`.
- Writes backend logs to:

```text
%LOCALAPPDATA%\RecipeAnalyzer\logs\backend.log
```

- Logs startup details:
  - executable path
  - current working directory
  - frozen status
  - app root
  - data dir
  - database path
  - seed database candidate paths and copy status
  - FastAPI import success/failure
  - uvicorn startup failure
- Copies the bundled seed database into `%LOCALAPPDATA%\RecipeAnalyzer\data\recipe_analyzer.db` when the local database is missing or still empty.
- Keeps an existing local database when it already contains recipe rows, so user data is not overwritten.

### Desktop seed database resource

File:

```text
src-tauri/tauri.conf.json
```

Change:

- Added bundle resource mapping:

```json
"../data/recipe_analyzer.db": "data/recipe_analyzer.db"
```

Verification:

- `src-tauri\target\release\data\recipe_analyzer.db` exists after build.
- Generated NSIS script copies it to `$INSTDIR\data\recipe_analyzer.db`.
- Source seed database currently contains `1342` recipe rows.

### Desktop source workbook resource

Files:

```text
src-tauri/tauri.conf.json
desktop/tauri_backend/recipe_backend_sidecar.py
backend/app/services/import_service.py
```

Changes:

- Bundle resource mapping now includes:

```json
"../data/recipes.xlsx": "data/recipes.xlsx"
```

- The sidecar copies bundled `recipes.xlsx` into `%LOCALAPPDATA%\RecipeAnalyzer\data\recipes.xlsx` when missing.
- `persist_import()` saves committed uploaded Excel bytes to `DATA_DIR\recipes.xlsx`.
- Pairing Review therefore has a workbook source in both dev web and installed exe environments.

Verification:

- `.\.venv\Scripts\python.exe -m py_compile backend\app\services\import_service.py desktop\tauri_backend\recipe_backend_sidecar.py`
- `npm --prefix frontend run build`
- `npm run desktop:build`
- `src-tauri\target\release\data\recipes.xlsx` exists after build.

### Frontend backend cold-start retry

File:

```text
frontend/src/lib/api.js
```

Change:

- In Tauri runtime, API requests use `http://127.0.0.1:8000/api`.
- Network-level fetch failures are retried up to 20 times with a 500ms delay to cover backend sidecar cold start.

### Ollama default model selection

Files:

```text
backend/app/services/ollama_service.py
frontend/src/components/AITools.jsx
```

Changes:

- Backend default fallback changed from `qwen3:0.6b` to `qwen3.5:4b`.
- `/api/ai/llm/status` now resolves `default_model` from installed Ollama models when `RECIPE_ANALYZER_OLLAMA_MODEL` is not explicitly set.
- Preference order is `qwen3.5:4b`, then `qwen3:4b`, then `qwen3:0.6b`, then the first installed model.
- Frontend no longer inserts `default_model` into the dropdown unless it exists in the installed model list.

Verified with:

```powershell
.\.venv\Scripts\python.exe -m py_compile backend\app\services\ollama_service.py
npm --prefix frontend run build
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

### Ollama reconnect button

Files:

```text
frontend/src/components/AITools.jsx
frontend/src/styles.css
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

Changes:

- Added `refreshLlmStatus()` in `AITools.jsx`.
- The AI header status pill now shows `重试连接` only when `llmStatus.available` is false.
- Clicking the button retries `/api/ai/llm/status`, `/api/ai/llm/models`, and DeepSeek key status.
- Button shows `连接中...` while retrying and is disabled during that request.
- App version bumped to `0.1.2` for upgrade installation.

Verified with:

```powershell
npm --prefix frontend run build
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

### AI chat process display

Files:

```text
frontend/src/components/AITools.jsx
frontend/src/styles.css
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

Changes:

- Replaced raw `思考过程` display with concise `处理过程` text based on the current pipeline stage.
- Removed frontend accumulation/display of `thinking_chunk` and `raw_thinking`.
- Chat requests now send `show_reasoning: false` so Ollama does not stream raw thinking text.
- The UI toggle label changed from `思考` to `过程`.
- Removed the long scroll behavior from the process panel.
- App version bumped to `0.1.3`.

Verified with:

```powershell
npm --prefix frontend run build
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

### Ollama thinking suppression

Files:

```text
backend/app/services/ollama_service.py
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

Changes:

- `_build_ollama_payload()` now sets top-level `think: false` when `include_thinking` is false.
- Removed the previous ineffective `options["thinking"] = False` approach.
- `_call_ollama_chat()` now passes content through `_strip_model_thinking()`.
- `_stream_ollama_chat()` buffers content when `include_thinking` is false, strips `ThinkingProcess:`/`<think>`-style output, then emits only the cleaned final answer.
- General chat system prompt now explicitly says to output only the final user-facing answer and not analysis, drafts, thinking, or internal English markers.
- App version bumped to `0.1.4`.

Verified with:

```powershell
.\.venv\Scripts\python.exe -m py_compile backend\app\services\ollama_service.py
npm --prefix frontend run build
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

### Backend process cleanup

Files:

```text
src-tauri/src/lib.rs
desktop/tauri_backend/recipe_backend_sidecar.py
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

Changes:

- Tauri app now uses `.build(...).run(...)` so it can catch `RunEvent::ExitRequested` and `RunEvent::Exit`.
- `stop_backend()` is called on both window close and app exit events.
- Before spawning a sidecar, Tauri terminates stale same-path `recipe-backend.exe` processes from the install directory. This cleans up old orphaned backends that predate the PID file.
- Sidecar writes `%LOCALAPPDATA%\RecipeAnalyzer\backend.pid` before starting uvicorn.
- On startup, sidecar reads that PID file and terminates the previous process only when its executable path matches the current sidecar path.
- If port 8000 already has a healthy backend after cleanup, the sidecar exits instead of entering an idle loop, so it no longer creates extra resident idle sidecars.
- App version bumped to `0.1.5`.

Verified with:

```powershell
.\.venv\Scripts\python.exe -m py_compile desktop\tauri_backend\recipe_backend_sidecar.py
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
cargo check
npm run desktop:build
```

### Desktop database export

Files:

```text
backend/app/api/routes/database.py
backend/app/services/database_transfer_service.py
frontend/src/lib/api.js
frontend/src/components/DatabaseBrowser.jsx
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

Changes:

- Added `POST /api/database/export-to-downloads`.
- Backend copies the current SQLite database to `~/Downloads` or `~/下载`, using a timestamped backup name and unique suffix if needed.
- Tauri frontend uses the new endpoint instead of an `<a download>` file stream.
- Browser frontend still uses the original `/api/database/export` download flow.
- Success message now shows the exact saved file path in desktop.
- App version bumped to `0.1.6`.

Verified with:

```powershell
.\.venv\Scripts\python.exe -m py_compile backend\app\api\routes\database.py backend\app\services\database_transfer_service.py
npm --prefix frontend run build
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

### Ingredient filter search

Files:

```text
frontend/src/components/RecipeList.jsx
frontend/src/styles.css
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

Changes:

- Replaced the recipe library `食材` native `<select>` with a custom searchable selector.
- The selector supports typing to filter ingredient names client-side.
- It displays all matching ingredient options instead of truncating the list.
- Selecting `全部` clears the ingredient filter.
- Other filters remain native selects.
- App version bumped to `0.1.7`.

Verified with:

```powershell
npm --prefix frontend run build
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

### Installer upgrade behavior

Files:

```text
package.json
src-tauri/Cargo.toml
src-tauri/tauri.conf.json
```

Changes:

- App version bumped from `0.1.0` to `0.1.1`.
- `bundle.windows.allowDowngrades` set to `false`.
- `bundle.windows.nsis.installMode` set to `currentUser` so updates keep using the same per-user registry/install location.

Verified generated NSIS script contains:

```text
!define VERSION "0.1.1"
!define INSTALLMODE "currentUser"
!define ALLOWDOWNGRADES "false"
```

The generated NSIS installer also supports update mode via command line:

```powershell
& ".\Recipe Analyzer_0.1.1_x64-setup.exe" /UPDATE
```

This proceeds without running the old uninstaller path. Double-clicking a higher-version installer may still show Tauri's upgrade choice page; choose the non-uninstall/direct-install option if prompted.

Verified with:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

### Tauri sidecar startup behavior

File:

```text
src-tauri/src/lib.rs
```

Changes:

- The app now manages `BackendProcess(None)` initially.
- If resolving or spawning the sidecar fails, the error is printed instead of making `.setup()` return an error.
- This should prevent the main Tauri window from immediately exiting solely because the backend sidecar failed.
- Sidecar spawning now uses `app.shell().sidecar("recipe-backend")` instead of `app.shell().sidecar("binaries/recipe-backend")`, matching the actual bundled executable location:

```text
<install-dir>\recipe-backend.exe
```

Verified with:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

The NSIS installer was regenerated at:

```text
src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.0_x64-setup.exe
```

Latest upgrade build:

```text
src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.1_x64-setup.exe
```

Note: the build still emitted a non-fatal MSI bundler-type patch warning caused by a file lock, but the NSIS installer was produced successfully.

### PyInstaller build workaround

Files:

```text
desktop/tauri_backend/build_sidecar.py
desktop/tauri_backend/build_backend_sidecar.bat
```

Reason:

- PyInstaller repeatedly failed on this machine with `PermissionError` while rewriting PE timestamp/checksum metadata.
- The workaround monkey-patches these optional PyInstaller Windows post-processing functions:
  - `winutils.set_exe_build_timestamp`
  - `winutils.update_exe_pe_checksum`

This is intentional and should remain unless the build environment changes.

## Current Packaging Commands

Build everything:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npm run desktop:build
```

Build just the sidecar:

```powershell
npm run sidecar:build
```

The sidecar executable should be copied to:

```text
src-tauri\binaries\recipe-backend-x86_64-pc-windows-msvc.exe
```

Tauri expects it through this config:

```json
"externalBin": [
  "binaries/recipe-backend"
]
```

## Immediate Next Debugging Step

Ask the user to install the newly rebuilt NSIS installer on the target machine and retry the app:

```text
src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.0_x64-setup.exe
```

Current latest installer:

```text
src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.1_x64-setup.exe
```

If the frontend still shows `Failed to fetch`, check:

```text
C:\Users\<username>\AppData\Local\RecipeAnalyzer\logs\backend.log
```

Also check whether this file exists and has roughly the bundled DB size:

```text
C:\Users\<username>\AppData\Local\RecipeAnalyzer\data\recipe_analyzer.db
```

If it is tiny or empty from an older failed run, the latest sidecar should replace it only when it has zero recipes.

If the log is still empty:

- The sidecar may not be launching at all.
- Check whether Windows Defender or another security tool is blocking/quarantining `recipe-backend.exe`.
- Check the installed app directory for whether the backend binary exists.
- Consider adding frontend-visible backend status diagnostics.

If the log has content:

- Use the first traceback or the last startup line to identify the failure stage:
  - before `_prepare_environment`
  - database path/copy failure
  - `from app.main import app` failure
  - uvicorn startup failure
  - port 8000 occupied
  - missing DLL or bundled Python dependency

## Important Known Issue: Encoding Display

Some files showed Chinese text as mojibake in terminal output when not explicitly read with UTF-8. The files themselves are UTF-8. Use:

```powershell
Get-Content -Encoding UTF8
```

or Python `Path.read_text(encoding="utf-8")`.

## AI Q&A Context Pollution Fix

Recent bug:

- User asked only for `请给3道牛肉菜`.
- Model still answered with `不辣` explanations.

Root cause:

- The answer-stage system prompt always contained the rule for "用户要求不辣时...".
- `qwen3:0.6b` treated it as part of the current task.

Fix:

File:

```text
backend/app/services/ollama_service.py
```

Changes:

- `_build_answer_system_prompt()` now injects condition-specific rules only when the current user message or interpretation explicitly mentions:
  - not spicy
  - rice pairing / 下饭
  - health-sensitive / 病号 / 减脂 etc.
- If none are mentioned, the prompt explicitly says not to introduce unrelated conditions like spicy, rice-pairing, patient food, or fat loss.

After backend restart, test:

```text
请给3道牛肉菜
```

Expected: no unnecessary spicy/non-spicy explanation.

## Recipe Detail Tooltip Change

Files:

```text
frontend/src/components/RecipeDetail.jsx
frontend/src/styles.css
```

Change:

- The long descriptions under:
  - `标准化食材（AI生成，仅供参考）`
  - `自动标签（AI生成，仅供参考）`
- were moved into a small `!` tooltip next to the section title.

Verified with:

```powershell
npm --prefix frontend run build
```

## DataHelper Latest Analysis

Latest database analyzed:

```text
miniappoutput\data_backup_0429v3 - refiner.db
```

Results:

- Official recipes: `1321`
- Refine states: `1321`
- Success: `1289`
- Failed: `32`
- Failure rate: about `2.4%`

Compared with earlier:

- `data_backup_0428 - refiner.db`: `345` failed
- `data_backup_0429 - refiner.db`: `282` failed
- `data_backup_0429v2 - refiner.db`: `281` failed
- `data_backup_0429v3 - refiner.db`: `32` failed

Remaining problems:

- Some failures are expected because source ingredient/seasoning text is empty.
- Some failures come from qwen outputting `Thinking Process:` instead of pure JSON.
- Some successful results are still poor long phrase ingredients.

Recommended next improvement:

- Add a separate status for empty source, such as `skipped_empty_source`, instead of counting it as failure.
- Strengthen post-success quality audit:
  - hide or rerun names that are too long
  - contain `见...词条`
  - contain full sentences
  - contain `也可以`, `总之`, `参考`, `基础上`

## Core Product Rules

- Original Excel-derived text is authoritative.
- Record detail must show original Excel ingredients, seasonings, and steps exactly as source text.
- Standardized ingredients and automatic tags are AI-generated reference data only.
- Excel import should remain incremental.
- AI refinement/tagging should remain incremental and should not rerun unchanged successful records unless quality audit flags them.

## DeepSeek Behavior

DeepSeek is used in two main ways:

- Ingredient visibility cleanup:
  - Only sends candidate ingredient terms.
  - Does not send dish names, steps, notes, or full recipes.
- AI Q&A:
  - Optional "DeepSeek前置解析": sends only the user question plus low-risk library vocabulary summary.
  - Optional "DeepSeek后处理": sends sanitized top candidate summaries only if user explicitly enables it.

DeepSeek API Key is saved through app settings and should not be hardcoded.

## Long Task Behavior

Long backend tasks include:

- Step1 local AI ingredient analysis.
- Step2 external AI messy ingredient removal.
- Automatic tagging.

Expected behavior:

- Switching web pages should not stop backend tasks.
- Closing the frontend usually does not stop backend tasks.
- Closing the backend process stops tasks.
- On backend restart, stale `running` jobs should be marked `paused`.

## Important Files

Backend routes:

```text
backend/app/api/routes/ai.py
backend/app/api/routes/imports.py
backend/app/api/routes/system.py
```

AI services:

```text
backend/app/services/ollama_service.py
backend/app/services/deepseek_service.py
backend/app/services/import_refine_service.py
backend/app/services/ingredient_visibility_service.py
backend/app/services/managed_tag_service.py
backend/app/services/search_service.py
```

Frontend:

```text
frontend/src/App.jsx
frontend/src/components/AITools.jsx
frontend/src/components/RecipeEditor.jsx
frontend/src/components/RecipeDetail.jsx
frontend/src/components/ImportRefinementPanel.jsx
frontend/src/components/TagManagement.jsx
frontend/src/styles.css
```

Desktop:

```text
src-tauri/
desktop/tauri_backend/
desktop/db_refiner/
desktop/db_tagger/
```

Docs:

```text
README.md
docs/user-manual.md
desktop/README.md
AGENTS.md
codex-handoff.md
```

## Suggested First Actions For Next Session

1. Read `AGENTS.md`.
2. Read this file.
3. Ask whether the latest installer with enhanced logging has been tested on the target computer.
4. If tested, inspect the target machine's `backend.log`.
5. If not tested, have the user install:

```text
src-tauri\target\release\bundle\nsis\Recipe Analyzer_0.1.0_x64-setup.exe
```

6. Continue packaging debug from the actual log content.
