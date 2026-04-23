import shutil
import sqlite3
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.config import DATA_DIR, DATABASE_PATH
from app.db.database import initialize_database
from app.services.search_service import rebuild_recipe_search_index


BACKUP_DIR = DATA_DIR / "backups"
IMPORT_LOCK = threading.Lock()
REQUIRED_TABLES = {
    "recipes",
    "ingredients",
    "recipe_ingredients",
    "import_batches",
}


def get_database_export_info() -> dict:
    database_path = Path(DATABASE_PATH)
    if not database_path.exists():
        raise FileNotFoundError("Database file does not exist")

    return {
        "path": database_path,
        "file_name": f"recipe_analyzer_backup_{datetime.now():%Y%m%d_%H%M%S}.db",
    }


def import_database_file(upload: UploadFile) -> dict:
    suffix = Path(upload.filename or "database.db").suffix.lower() or ".db"
    if suffix not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Only .db, .sqlite, or .sqlite3 files are supported")

    database_path = Path(DATABASE_PATH)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    backup_path = None

    with IMPORT_LOCK:
        temp_path = _write_upload_to_tempfile(upload, suffix)
        try:
            _validate_sqlite_database(temp_path)

            if database_path.exists():
                backup_path = BACKUP_DIR / f"recipe_analyzer_pre_import_{datetime.now():%Y%m%d_%H%M%S}.db"
                shutil.copy2(database_path, backup_path)

            shutil.copy2(temp_path, database_path)
            initialize_database()
            rebuild_recipe_search_index()
        finally:
            temp_path.unlink(missing_ok=True)

    return {
        "status": "ok",
        "database_file": database_path.name,
        "backup_file": backup_path.name if backup_path else None,
    }


def _write_upload_to_tempfile(upload: UploadFile, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            temp_file.write(chunk)
        return Path(temp_file.name)


def _validate_sqlite_database(path: Path) -> None:
    try:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as error:
        raise ValueError(f"Invalid SQLite database: {error}") from error

    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"SQLite integrity check failed: {integrity}")

        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }
        missing_tables = sorted(REQUIRED_TABLES - tables)
        if missing_tables:
            raise ValueError(f"Database is missing required tables: {', '.join(missing_tables)}")
    finally:
        connection.close()
