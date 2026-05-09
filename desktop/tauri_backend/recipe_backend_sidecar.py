import os
import shutil
import signal
import sqlite3
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import uvicorn


HOST = "127.0.0.1"
PORT = 8000
HEALTH_URL = f"http://{HOST}:{PORT}/api/health"
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _default_app_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "RecipeAnalyzer"


def _pid_file_path() -> Path:
    return _default_app_data_dir() / "backend.pid"


def _candidate_seed_database_paths(executable_dir: Path) -> list[Path]:
    return [
        executable_dir / "data" / "recipe_analyzer.db",
        executable_dir / "resources" / "data" / "recipe_analyzer.db",
        executable_dir.parent / "data" / "recipe_analyzer.db",
        Path.cwd() / "data" / "recipe_analyzer.db",
    ]


def _candidate_source_workbook_paths(executable_dir: Path) -> list[Path]:
    return [
        executable_dir / "data" / "recipes.xlsx",
        executable_dir / "resources" / "data" / "recipes.xlsx",
        executable_dir.parent / "data" / "recipes.xlsx",
        Path.cwd() / "data" / "recipes.xlsx",
    ]


def _database_recipe_count(database_path: Path) -> int:
    if not database_path.exists():
        return 0

    try:
        with sqlite3.connect(database_path) as connection:
            table_exists = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = 'recipes'
                """
            ).fetchone()
            if table_exists is None:
                return 0
            return int(connection.execute("SELECT COUNT(*) FROM recipes").fetchone()[0])
    except sqlite3.Error:
        return 0


def _copy_seed_database_if_needed(database_path: Path, executable_dir: Path) -> None:
    if database_path.exists() and _database_recipe_count(database_path) > 0:
        _log(f"Existing database has data; keeping {database_path}")
        return

    for seed_path in _candidate_seed_database_paths(executable_dir):
        _log(f"Checking seed database candidate: {seed_path}")
        if seed_path.exists():
            database_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seed_path, database_path)
            _log(f"Seed database copied from {seed_path} to {database_path}")
            return

    if database_path.exists():
        _log(f"No seed database found; keeping existing empty database at {database_path}")
    else:
        _log(f"No seed database found; backend will create an empty database at {database_path}")


def _copy_source_workbook_if_needed(app_data_dir: Path, executable_dir: Path) -> None:
    workbook_path = app_data_dir / "recipes.xlsx"
    if workbook_path.exists():
        _log(f"Existing source workbook found; keeping {workbook_path}")
        return

    for source_path in _candidate_source_workbook_paths(executable_dir):
        _log(f"Checking source workbook candidate: {source_path}")
        if source_path.exists():
            workbook_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, workbook_path)
            _log(f"Source workbook copied from {source_path} to {workbook_path}")
            return

    _log("No source workbook found; pairing review will be unavailable until an Excel import is committed")


def _prepare_environment() -> None:
    executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    app_data_dir = Path(os.getenv("RECIPE_ANALYZER_DATA_DIR", str(_default_app_data_dir() / "data")))
    app_data_dir.mkdir(parents=True, exist_ok=True)

    database_path = Path(os.getenv("RECIPE_ANALYZER_DB_PATH", str(app_data_dir / "recipe_analyzer.db")))
    _copy_seed_database_if_needed(database_path, executable_dir)
    _copy_source_workbook_if_needed(app_data_dir, executable_dir)

    os.environ.setdefault("RECIPE_ANALYZER_APP_ROOT", str(executable_dir))
    os.environ.setdefault("RECIPE_ANALYZER_DATA_DIR", str(app_data_dir))
    os.environ.setdefault("RECIPE_ANALYZER_DB_PATH", str(database_path))
    for desktop_exe in (
        executable_dir / "recipe-analyzer.exe",
        executable_dir / "Recipe Analyzer.exe",
    ):
        if desktop_exe.exists():
            os.environ.setdefault("RECIPE_ANALYZER_DESKTOP_EXE", str(desktop_exe))
            break


_stdio_log_handle = None


def _prepare_stdio() -> None:
    global _stdio_log_handle

    log_dir = _default_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _stdio_log_handle = open(log_dir / "backend.log", "a", encoding="utf-8", buffering=1)

    if sys.stdout is None:
        sys.stdout = _stdio_log_handle
    if sys.stderr is None:
        sys.stderr = _stdio_log_handle


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _is_existing_backend_healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            return response.status == 200 and b"recipe-analyzer-api" in response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _query_process_image_path(pid: int) -> Optional[Path]:
    if os.name != "nt":
        return None

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None

        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            return Path(buffer.value).resolve()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def _terminate_process(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False

    for _ in range(20):
        time.sleep(0.1)
        if _query_process_image_path(pid) is None:
            return True
    return True


def _cleanup_previous_backend_process(current_executable: Path) -> None:
    pid_file = _pid_file_path()
    try:
        previous_pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return

    if previous_pid == os.getpid():
        return

    previous_path = _query_process_image_path(previous_pid)
    if previous_path is None:
        _log(f"Removing stale backend pid file for pid={previous_pid}")
        pid_file.unlink(missing_ok=True)
        return

    if previous_path != current_executable:
        _log(f"Previous backend pid={previous_pid} belongs to {previous_path}; not terminating")
        return

    _log(f"Terminating previous backend sidecar pid={previous_pid}")
    if _terminate_process(previous_pid):
        pid_file.unlink(missing_ok=True)


def _write_pid_file() -> None:
    pid_file = _pid_file_path()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    _log(f"Wrote backend pid file: {pid_file}")


def main() -> None:
    _prepare_stdio()
    executable_path = Path(sys.executable).resolve()
    _log("Recipe backend sidecar starting")
    _log(f"executable={executable_path}")
    _log(f"cwd={Path.cwd()}")
    _log(f"frozen={getattr(sys, 'frozen', False)}")

    preserve_existing_backend = os.getenv("RECIPE_ANALYZER_PRESERVE_BACKEND") == "1"
    if preserve_existing_backend:
        _log("Preserving existing backend process because RECIPE_ANALYZER_PRESERVE_BACKEND=1")
    else:
        _cleanup_previous_backend_process(executable_path)

    try:
        _prepare_environment()
        _log(f"RECIPE_ANALYZER_APP_ROOT={os.getenv('RECIPE_ANALYZER_APP_ROOT')}")
        _log(f"RECIPE_ANALYZER_DATA_DIR={os.getenv('RECIPE_ANALYZER_DATA_DIR')}")
        _log(f"RECIPE_ANALYZER_DB_PATH={os.getenv('RECIPE_ANALYZER_DB_PATH')}")
    except Exception:
        _log("Environment preparation failed")
        traceback.print_exc()
        raise

    if _is_existing_backend_healthy():
        _log("Existing backend on port 8000 is healthy; sidecar exiting instead of idling")
        return

    try:
        from app.main import app
        _log("Imported FastAPI app")
    except Exception:
        _log("Failed to import FastAPI app")
        traceback.print_exc()
        raise

    try:
        _log(f"Starting uvicorn on {HOST}:{PORT}")
        _write_pid_file()
        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            log_config=None,
            log_level="warning",
            access_log=False,
        )
    except Exception:
        _log("Uvicorn failed")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if sys.stderr is not None:
            traceback.print_exc()
        time.sleep(3)
        raise
