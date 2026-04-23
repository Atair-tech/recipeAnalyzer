import json
from typing import Any, Dict, Optional

from app.db.database import get_connection
from app.services.import_refine_service import (
    _apply_refined_recipe,
    _build_refine_version,
    _generate_refined_ingredients,
    _load_recipe_snapshot,
    _store_refine_snapshot,
)
from app.services.ollama_service import OLLAMA_DEFAULT_MODEL
from app.services.recipe_service import get_recipe


VALID_REVIEW_STATUSES = {"approved", "issue"}


def list_refine_review_items(
    search: Optional[str] = None,
    status: str = "all",
    limit: int = 200,
) -> Dict[str, Any]:
    where_clauses = ["r.record_kind = 'recipe'"]
    params = []

    if search:
        where_clauses.append(
            """
            (
                r.name LIKE ?
                OR COALESCE(r.library_section, '') LIKE ?
                OR COALESCE(r.section_name, '') LIKE ?
            )
            """
        )
        pattern = f"%{search.strip()}%"
        params.extend([pattern, pattern, pattern])

    if status == "pending":
        where_clauses.append("rr.status IS NULL")
    elif status == "approved":
        where_clauses.append("rr.status = 'approved'")
    elif status == "issue":
        where_clauses.append("rr.status = 'issue'")
    elif status == "error":
        where_clauses.append("rs.last_error IS NOT NULL AND TRIM(rs.last_error) <> ''")

    params.append(limit)

    query = f"""
        SELECT
            r.id,
            r.name,
            r.library_section,
            r.section_name,
            r.updated_at,
            rs.model AS refine_model,
            rs.refine_version,
            rs.refined_at,
            rs.last_error,
            rr.status AS review_status,
            rr.note AS review_note,
            rr.updated_at AS review_updated_at,
            COUNT(ri.id) AS ingredient_count
        FROM recipes AS r
        LEFT JOIN recipe_ai_refine_state AS rs ON rs.recipe_id = r.id
        LEFT JOIN recipe_refine_reviews AS rr ON rr.recipe_id = r.id
        LEFT JOIN recipe_ingredients AS ri ON ri.recipe_id = r.id
        WHERE {' AND '.join(where_clauses)}
        GROUP BY
            r.id,
            r.name,
            r.library_section,
            r.section_name,
            r.updated_at,
            rs.model,
            rs.refine_version,
            rs.refined_at,
            rs.last_error,
            rr.status,
            rr.note,
            rr.updated_at
        ORDER BY
            CASE
                WHEN rs.last_error IS NOT NULL AND TRIM(rs.last_error) <> '' THEN 0
                WHEN rr.status = 'issue' THEN 1
                WHEN rr.status IS NULL THEN 2
                ELSE 3
            END,
            datetime(COALESCE(rs.refined_at, r.updated_at)) DESC,
            r.id DESC
        LIMIT ?
    """

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "library_section": row["library_section"],
                "section_name": row["section_name"],
                "updated_at": row["updated_at"],
                "ingredient_count": row["ingredient_count"] or 0,
                "refine_model": row["refine_model"],
                "refine_version": row["refine_version"],
                "refined_at": row["refined_at"],
                "last_error": row["last_error"],
                "review_status": row["review_status"] or "pending",
                "review_note": row["review_note"],
                "review_updated_at": row["review_updated_at"],
            }
            for row in rows
        ]
    }


def get_refine_review_detail(recipe_id: int) -> Optional[Dict[str, Any]]:
    recipe = get_recipe(recipe_id)
    if recipe is None:
        return None

    with get_connection() as connection:
        refine_state = connection.execute(
            """
            SELECT recipe_id, source_hash, model, refine_version, refined_at, last_run_id, last_error
            FROM recipe_ai_refine_state
            WHERE recipe_id = ?
            """,
            (recipe_id,),
        ).fetchone()
        review_state = connection.execute(
            """
            SELECT recipe_id, status, note, updated_at
            FROM recipe_refine_reviews
            WHERE recipe_id = ?
            """,
            (recipe_id,),
        ).fetchone()
        snapshot_row = connection.execute(
            """
            SELECT
                id,
                run_id,
                model,
                refine_version,
                before_ingredients_json,
                after_ingredients_json,
                created_at
            FROM recipe_refine_snapshots
            WHERE recipe_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (recipe_id,),
        ).fetchone()

    return {
        "recipe": recipe,
        "refine_state": dict(refine_state) if refine_state is not None else None,
        "snapshot": (
            {
                "id": snapshot_row["id"],
                "run_id": snapshot_row["run_id"],
                "model": snapshot_row["model"],
                "refine_version": snapshot_row["refine_version"],
                "before_ingredients": json.loads(snapshot_row["before_ingredients_json"] or "[]"),
                "after_ingredients": json.loads(snapshot_row["after_ingredients_json"] or "[]"),
                "created_at": snapshot_row["created_at"],
            }
            if snapshot_row is not None
            else None
        ),
        "review": (
            {
                "status": review_state["status"],
                "note": review_state["note"],
                "updated_at": review_state["updated_at"],
            }
            if review_state is not None
            else {
                "status": "pending",
                "note": "",
                "updated_at": None,
            }
        ),
    }


def update_refine_review(recipe_id: int, status: str, note: Optional[str] = None) -> Dict[str, Any]:
    normalized_status = (status or "").strip().lower()
    if normalized_status not in VALID_REVIEW_STATUSES:
        raise ValueError("Invalid review status")

    normalized_note = (note or "").strip() or None

    with get_connection() as connection:
        recipe_exists = connection.execute("SELECT 1 FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if recipe_exists is None:
            raise ValueError("Recipe not found")

        connection.execute(
            """
            INSERT INTO recipe_refine_reviews (recipe_id, status, note, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(recipe_id) DO UPDATE SET
                status = excluded.status,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            (recipe_id, normalized_status, normalized_note),
        )
        connection.commit()

    return get_refine_review_detail(recipe_id)


def rerun_refine_recipe(recipe_id: int, model: Optional[str] = None) -> Dict[str, Any]:
    snapshot = _load_recipe_snapshot(recipe_id)
    if not snapshot:
        raise ValueError("Recipe not found")

    with get_connection() as connection:
        state_row = connection.execute(
            "SELECT source_hash, model FROM recipe_ai_refine_state WHERE recipe_id = ?",
            (recipe_id,),
        ).fetchone()
        recipe_row = connection.execute("SELECT source_hash FROM recipes WHERE id = ?", (recipe_id,)).fetchone()

    model_name = (
        (model or "").strip()
        or (state_row["model"] if state_row is not None and state_row["model"] else "")
        or OLLAMA_DEFAULT_MODEL
    )
    source_hash = recipe_row["source_hash"] if recipe_row is not None else None
    refine_version = _build_refine_version()
    refined = _generate_refined_ingredients(snapshot, model_name)

    with get_connection() as connection:
        _store_refine_snapshot(
            connection,
            recipe_id=recipe_id,
            run_id=None,
            model_name=model_name,
            refine_version=refine_version,
            before_ingredients=snapshot["ingredients"],
            after_ingredients=refined["ingredients"],
        )
        _apply_refined_recipe(connection, recipe_id, refined)
        connection.execute(
            """
            INSERT INTO recipe_ai_refine_state (
                recipe_id,
                source_hash,
                model,
                refine_version,
                refined_at,
                last_run_id,
                last_error
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, NULL, NULL)
            ON CONFLICT(recipe_id) DO UPDATE SET
                source_hash = excluded.source_hash,
                model = excluded.model,
                refine_version = excluded.refine_version,
                refined_at = CURRENT_TIMESTAMP,
                last_run_id = NULL,
                last_error = NULL
            """,
            (recipe_id, source_hash, model_name, refine_version),
        )
        connection.commit()

    return get_refine_review_detail(recipe_id)
