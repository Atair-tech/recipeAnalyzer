import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
DATA_DIR = REPO_ROOT / "data"
DATABASE_PATH = Path(
    os.getenv("RECIPE_ANALYZER_DB_PATH", str(DATA_DIR / "recipe_analyzer.db"))
)

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
