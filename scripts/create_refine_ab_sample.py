import argparse
import csv
import json
import random
import sqlite3
from pathlib import Path


DEFAULT_OUTPUT = Path("data/runtime/refine_ab_sample.csv")
DB_PATH = Path("data/recipe_analyzer.db")


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def classify_complexity(row: sqlite3.Row) -> tuple[str, int]:
    text = " ".join(
        [
            row["ingredients_text"] or "",
            row["seasonings_text"] or "",
            row["notes_text"] or "",
            row["source_text"] or "",
        ]
    )

    score = 0
    score += text.count("（") + text.count("(")
    score += text.count("也可") * 2
    score += text.count("可用") * 2
    score += text.count("可加") * 2
    score += text.count("推荐") * 2
    score += text.count("建议") * 2
    score += text.count("/") * 2
    score += text.lower().count("or") * 2
    score += text.count("%") * 3
    score += text.count("来源文本") * 4

    if score <= 2:
        return "simple", score
    if score <= 7:
        return "medium", score
    return "complex", score


def fetch_candidates(connection: sqlite3.Connection) -> list[dict]:
    recipe_rows = connection.execute(
        """
        SELECT
            r.id,
            r.name,
            r.ingredients_text,
            r.seasonings_text,
            r.notes_text,
            r.source_text
        FROM recipes r
        WHERE r.record_kind = 'recipe'
        ORDER BY r.id
        """
    ).fetchall()

    candidates = []
    for row in recipe_rows:
        ingredients = connection.execute(
            """
            SELECT i.name, ri.amount, ri.unit, ri.remark
            FROM recipe_ingredients ri
            INNER JOIN ingredients i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            ORDER BY ri.id
            """,
            (row["id"],),
        ).fetchall()
        tier, score = classify_complexity(row)
        candidates.append(
            {
                "recipe_id": row["id"],
                "name": row["name"],
                "tier": tier,
                "complexity_score": score,
                "ingredients_text": row["ingredients_text"] or "",
                "seasonings_text": row["seasonings_text"] or "",
                "notes_text": row["notes_text"] or "",
                "source_text": row["source_text"] or "",
                "current_structured_ingredients": json.dumps(
                    [
                        {
                            "name": ingredient["name"],
                            "amount": ingredient["amount"],
                            "unit": ingredient["unit"],
                            "remark": ingredient["remark"],
                        }
                        for ingredient in ingredients
                    ],
                    ensure_ascii=False,
                ),
            }
        )
    return candidates


def sample_candidates(candidates: list[dict], per_tier: int, seed: int) -> list[dict]:
    random.seed(seed)
    selected: list[dict] = []
    for tier in ("simple", "medium", "complex"):
        bucket = [item for item in candidates if item["tier"] == tier]
        random.shuffle(bucket)
        selected.extend(bucket[:per_tier])
    return sorted(selected, key=lambda item: (item["tier"], item["recipe_id"]))


def write_csv(output_path: Path, rows: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "recipe_id",
        "name",
        "tier",
        "complexity_score",
        "ingredients_text",
        "seasonings_text",
        "notes_text",
        "source_text",
        "current_structured_ingredients",
        "review_status",
        "review_notes",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["review_status"] = ""
            row["review_notes"] = ""
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a refinement A/B sample review sheet.")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite database path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV output path")
    parser.add_argument("--per-tier", type=int, default=20, help="Number of recipes per complexity tier")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    db_path = Path(args.db)
    output_path = Path(args.output)

    with connect(db_path) as connection:
        candidates = fetch_candidates(connection)

    sampled = sample_candidates(candidates, per_tier=args.per_tier, seed=args.seed)
    write_csv(output_path, sampled)
    print(f"Wrote {len(sampled)} rows to {output_path}")


if __name__ == "__main__":
    main()
