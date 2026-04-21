import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingredient_service import sync_recipe_ingredients
DB_PATH = REPO_ROOT / "data" / "recipe_analyzer.db"


def main() -> None:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")

    try:
        recipe_rows = connection.execute(
            """
            SELECT id, ingredients_text
            FROM recipes
            ORDER BY id
            """
        ).fetchall()

        connection.execute("DELETE FROM recipe_ingredients")
        connection.execute("DELETE FROM ingredients")

        for row in recipe_rows:
            sync_recipe_ingredients(connection, row["id"], row["ingredients_text"])

        connection.commit()

        ingredient_count = connection.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
        relation_count = connection.execute("SELECT COUNT(*) FROM recipe_ingredients").fetchone()[0]
        print(
            {
                "recipes_processed": len(recipe_rows),
                "ingredient_count": ingredient_count,
                "recipe_ingredient_count": relation_count,
            }
        )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
