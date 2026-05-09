# Desktop Packaging

The desktop app uses Tauri as the native shell and starts the FastAPI backend as a sidecar process.

## Structure

- `src-tauri/`: Tauri v2 shell.
- `desktop/tauri_backend/`: Python sidecar entrypoint and build script.
- `desktop/db_refiner/`: standalone DataHelper.
- `desktop/db_tagger/`: standalone LabelHelper.

## Build Prerequisites

- Node.js and npm.
- Python virtual environment from the main project.
- Rust toolchain with `cargo` available on PATH.
- Windows WebView2 runtime.

Rust is required by Tauri. If `cargo --version` fails, install Rust first from `https://rustup.rs`.

## Development Run

Build the backend sidecar first:

```powershell
npm run sidecar:build
```

Then run Tauri dev:

```powershell
npm run tauri:dev
```

## Production Build

```powershell
npm run desktop:build
```

This runs:

1. `desktop\tauri_backend\build_backend_sidecar.bat`
2. `npm --prefix frontend run build`
3. `tauri build`

The desktop backend stores runtime data under:

```text
%LOCALAPPDATA%\RecipeAnalyzer\data
```

This keeps the packaged installation directory read-only and preserves the SQLite database across app upgrades.
