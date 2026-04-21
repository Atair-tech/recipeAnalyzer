from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import DATA_DIR
from app.db.database import get_connection
from app.services.workbook_parser import parse_recipe_workbook


SOURCE_WORKBOOK_PATH = DATA_DIR / "recipes.xlsx"


def get_pairing_review() -> Dict[str, Any]:
    raw_bytes = _read_source_workbook()
    overrides = load_pair_overrides()
    parsed = parse_recipe_workbook(raw_bytes, pair_overrides=overrides, include_review=True)

    sections = sorted(
        parsed["pairing_review"],
        key=lambda item: (-(item["index_only_count"] + item["detail_only_count"]), item["library_section"]),
    )

    return {
        "source_file_name": SOURCE_WORKBOOK_PATH.name,
        "summary": parsed["summary"],
        "sections": sections,
        "overrides": overrides,
    }


def load_pair_overrides() -> List[Dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                library_section,
                index_ref,
                index_name,
                detail_ref,
                detail_name,
                created_at
            FROM recipe_pair_overrides
            ORDER BY library_section, index_name, detail_name
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "library_section": row["library_section"],
            "index_ref": row["index_ref"],
            "index_name": row["index_name"],
            "detail_ref": row["detail_ref"],
            "detail_name": row["detail_name"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_pair_override(
    library_section: str,
    index_name: str,
    detail_name: str,
    index_ref: Optional[str] = None,
    detail_ref: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_library_section = _normalize_required(library_section, "library_section")
    normalized_index_name = _normalize_required(index_name, "index_name")
    normalized_detail_name = _normalize_required(detail_name, "detail_name")
    normalized_index_ref = _normalize_optional(index_ref)
    normalized_detail_ref = _normalize_optional(detail_ref)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO recipe_pair_overrides (
                library_section,
                index_ref,
                index_name,
                detail_ref,
                detail_name
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                normalized_library_section,
                normalized_index_ref,
                normalized_index_name,
                normalized_detail_ref,
                normalized_detail_name,
            ),
        )
        connection.commit()

        if normalized_index_ref or normalized_detail_ref:
            row = connection.execute(
                """
                SELECT
                    id,
                    library_section,
                    index_ref,
                    index_name,
                    detail_ref,
                    detail_name,
                    created_at
                FROM recipe_pair_overrides
                WHERE library_section = ?
                  AND COALESCE(index_ref, index_name) = COALESCE(?, ?)
                  AND COALESCE(detail_ref, detail_name) = COALESCE(?, ?)
                """,
                (
                    normalized_library_section,
                    normalized_index_ref,
                    normalized_index_name,
                    normalized_detail_ref,
                    normalized_detail_name,
                ),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT
                    id,
                    library_section,
                    index_ref,
                    index_name,
                    detail_ref,
                    detail_name,
                    created_at
                FROM recipe_pair_overrides
                WHERE library_section = ?
                  AND index_name = ?
                  AND detail_name = ?
                """,
                (normalized_library_section, normalized_index_name, normalized_detail_name),
            ).fetchone()

    return {
        "id": row["id"],
        "library_section": row["library_section"],
        "index_ref": row["index_ref"],
        "index_name": row["index_name"],
        "detail_ref": row["detail_ref"],
        "detail_name": row["detail_name"],
        "created_at": row["created_at"],
    }


def create_pair_overrides_bulk(items: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    created_items: List[Dict[str, Any]] = []
    seen_keys = set()

    for item in items:
        library_section = _normalize_required(item.get("library_section", ""), "library_section")
        index_name = _normalize_required(item.get("index_name", ""), "index_name")
        detail_name = _normalize_required(item.get("detail_name", ""), "detail_name")
        index_ref = _normalize_optional(item.get("index_ref"))
        detail_ref = _normalize_optional(item.get("detail_ref"))
        dedupe_key = (library_section, index_ref or index_name, detail_ref or detail_name)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        created_items.append(
            create_pair_override(
                library_section=library_section,
                index_name=index_name,
                detail_name=detail_name,
                index_ref=index_ref,
                detail_ref=detail_ref,
            )
        )

    return created_items


def delete_pair_override(override_id: int) -> bool:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM recipe_pair_overrides WHERE id = ?",
            (override_id,),
        ).fetchone()
        if existing is None:
            return False

        connection.execute(
            "DELETE FROM recipe_pair_overrides WHERE id = ?",
            (override_id,),
        )
        connection.commit()
    return True


def _read_source_workbook() -> bytes:
    if not SOURCE_WORKBOOK_PATH.exists():
        raise ValueError(f"源工作簿不存在：{SOURCE_WORKBOOK_PATH}")
    return SOURCE_WORKBOOK_PATH.read_bytes()


def _normalize_required(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"Missing required field: {field_name}")
    return normalized


def _normalize_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
