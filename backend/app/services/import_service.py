import hashlib
import json
from typing import Any, BinaryIO, Dict, List, Optional

from app.db.database import get_connection
from app.services.ingredient_service import sync_recipe_ingredients
from app.services.pairing_service import load_pair_overrides
from app.services.search_service import rebuild_recipe_search_index
from app.services.workbook_parser import (
    ParsedRecord,
    parse_recipe_workbook,
    serialize_raw_payload,
)


IMPORT_FIELDS = [
    {"key": "record_kind", "label": "记录类型"},
    {"key": "name", "label": "名称"},
    {"key": "library_section", "label": "专题库"},
    {"key": "section_name", "label": "分组"},
    {"key": "cuisine", "label": "菜系"},
    {"key": "sub_cuisine", "label": "亚菜系"},
    {"key": "bmd_flag", "label": "BMD"},
    {"key": "cc_flag", "label": "CC"},
    {"key": "last_reviewed_on", "label": "最后记录日期"},
    {"key": "source_reference", "label": "来源/修订备注"},
    {"key": "ingredients_text", "label": "食材"},
    {"key": "seasonings_text", "label": "调料"},
    {"key": "steps_text", "label": "做法及要点"},
    {"key": "notes_text", "label": "系统备注"},
]


def preview_import(
    file_name: str,
    file_stream: BinaryIO,
    mapping_override: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    del mapping_override
    raw_bytes = file_stream.read()
    if not raw_bytes:
        raise ValueError("上传的 Excel 文件为空。")

    parsed = parse_recipe_workbook(raw_bytes, pair_overrides=load_pair_overrides())
    summary = parsed["summary"]

    return {
        "file_name": file_name,
        "mode": "structured_workbook",
        "parser_kind": parsed["parser_kind"],
        "fields": IMPORT_FIELDS,
        "sheet_names": parsed["sheet_names"],
        "summary": summary,
        "total_rows": summary["total_records"],
        "preview_rows": parsed["preview_rows"],
    }


def persist_import(
    file_name: str,
    file_stream: BinaryIO,
    mapping_override: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    del mapping_override
    raw_bytes = file_stream.read()
    if not raw_bytes:
        raise ValueError("上传的 Excel 文件为空。")

    parsed = parse_recipe_workbook(raw_bytes, pair_overrides=load_pair_overrides())
    prepared_rows: List[ParsedRecord] = parsed["records"]
    summary = parsed["summary"]

    with get_connection() as connection:
        _deduplicate_existing_recipes(connection)
        batch_cursor = connection.execute(
            """
            INSERT INTO import_batches (file_name, raw_meta)
            VALUES (?, ?)
            """,
            (
                file_name,
                json.dumps(
                    {
                        "mode": "structured_workbook",
                        "parser_kind": parsed["parser_kind"],
                        "sheet_names": parsed["sheet_names"],
                        "summary": summary,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        batch_id = batch_cursor.lastrowid

        _persist_raw_import_rows(connection, batch_id, prepared_rows)

        existing_recipes = _load_existing_recipes(connection)
        stats = {"added": 0, "updated": 0, "deleted": 0, "unchanged": 0}
        imported_source_keys = set()

        for prepared in prepared_rows:
            recipe_payload = prepared.recipe_payload
            source_key = prepared.source_key
            source_hash = _build_source_hash(prepared.source_hash_payload)
            imported_source_keys.add(source_key)

            existing = existing_recipes.get(source_key)
            if existing is None:
                recipe_id = _insert_recipe(connection, recipe_payload, source_key, source_hash, batch_id)
                _replace_recipe_tags(connection, recipe_id, recipe_payload["tags"])
                sync_recipe_ingredients(connection, recipe_id, recipe_payload["ingredients_text"])
                stats["added"] += 1
                continue

            if existing["source_hash"] == source_hash:
                stats["unchanged"] += 1
                continue

            _update_recipe(connection, existing["id"], recipe_payload, source_key, source_hash, batch_id)
            _replace_recipe_tags(connection, existing["id"], recipe_payload["tags"])
            sync_recipe_ingredients(connection, existing["id"], recipe_payload["ingredients_text"])
            stats["updated"] += 1

        recipe_ids_to_delete = [
            row["id"]
            for key, row in existing_recipes.items()
            if key not in imported_source_keys
        ]
        if recipe_ids_to_delete:
            placeholders = ", ".join("?" for _ in recipe_ids_to_delete)
            connection.execute(
                f"DELETE FROM recipes WHERE id IN ({placeholders})",
                recipe_ids_to_delete,
            )
            stats["deleted"] = len(recipe_ids_to_delete)

        _delete_unused_tags(connection)
        _delete_unused_ingredients(connection)
        rebuild_recipe_search_index(connection)
        connection.commit()

        saved_tag_count = connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    return {
        "mode": "structured_workbook",
        "parser_kind": parsed["parser_kind"],
        "batch_id": batch_id,
        "saved_raw_rows": len(prepared_rows),
        "added_recipes": stats["added"],
        "updated_recipes": stats["updated"],
        "deleted_recipes": stats["deleted"],
        "unchanged_recipes": stats["unchanged"],
        "saved_tags": saved_tag_count,
        "summary": summary,
    }


def list_import_batches(limit: int = 20) -> Dict[str, Any]:
    safe_limit = max(1, min(limit, 100))

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                b.id,
                b.file_name,
                b.imported_at,
                b.raw_meta,
                COUNT(r.id) AS raw_row_count
            FROM import_batches AS b
            LEFT JOIN raw_import_rows AS r ON r.batch_id = b.id
            GROUP BY b.id
            ORDER BY datetime(b.imported_at) DESC, b.id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    items = []
    for row in rows:
        raw_meta = _safe_json_loads(row["raw_meta"])
        summary = raw_meta.get("summary", {})
        items.append(
            {
                "id": row["id"],
                "file_name": row["file_name"],
                "imported_at": row["imported_at"],
                "raw_row_count": row["raw_row_count"],
                "mode": raw_meta.get("mode", "unknown"),
                "parser_kind": raw_meta.get("parser_kind"),
                "recipe_records": summary.get("recipe_records", 0),
                "backlog_records": summary.get("backlog_records", 0),
                "paired_recipes": summary.get("paired_recipes", 0),
                "index_only_recipes": summary.get("index_only_recipes", 0),
                "detail_only_recipes": summary.get("detail_only_recipes", 0),
                "library_sections": summary.get("library_sections", []),
            }
        )

    return {"items": items}


def get_import_batch_detail(batch_id: int, row_limit: int = 20) -> Optional[Dict[str, Any]]:
    safe_limit = max(1, min(row_limit, 100))

    with get_connection() as connection:
        batch_row = connection.execute(
            """
            SELECT
                b.id,
                b.file_name,
                b.imported_at,
                b.raw_meta,
                COUNT(r.id) AS raw_row_count
            FROM import_batches AS b
            LEFT JOIN raw_import_rows AS r ON r.batch_id = b.id
            WHERE b.id = ?
            GROUP BY b.id
            """,
            (batch_id,),
        ).fetchone()

        if batch_row is None:
            return None

        row_entries = connection.execute(
            """
            SELECT
                id,
                row_index,
                raw_json,
                parse_status,
                parse_result_json
            FROM raw_import_rows
            WHERE batch_id = ?
            ORDER BY row_index
            LIMIT ?
            """,
            (batch_id, safe_limit),
        ).fetchall()

    raw_meta = _safe_json_loads(batch_row["raw_meta"])
    rows = []
    for row_entry in row_entries:
        parse_result = _safe_json_loads(row_entry["parse_result_json"])
        rows.append(
            {
                "id": row_entry["id"],
                "row_index": row_entry["row_index"],
                "parse_status": row_entry["parse_status"],
                "raw_row": _safe_json_loads(row_entry["raw_json"]),
                "mapped_row": parse_result.get("mapped_row"),
                "source_key": parse_result.get("source_key"),
                "source_hash": parse_result.get("source_hash"),
            }
        )

    return {
        "id": batch_row["id"],
        "file_name": batch_row["file_name"],
        "imported_at": batch_row["imported_at"],
        "raw_row_count": batch_row["raw_row_count"],
        "mode": raw_meta.get("mode", "unknown"),
        "parser_kind": raw_meta.get("parser_kind"),
        "summary": raw_meta.get("summary", {}),
        "sheet_names": raw_meta.get("sheet_names", []),
        "fields": IMPORT_FIELDS,
        "rows": rows,
    }


def _persist_raw_import_rows(connection, batch_id: int, records: List[ParsedRecord]) -> None:
    for row_index, prepared in enumerate(records, start=1):
        source_hash = _build_source_hash(prepared.source_hash_payload)
        connection.execute(
            """
            INSERT INTO raw_import_rows (
                batch_id,
                row_index,
                raw_json,
                parse_status,
                parse_result_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                row_index,
                serialize_raw_payload(prepared.raw_payload),
                "parsed",
                json.dumps(
                    {
                        "mapped_row": _build_mapped_row(prepared.recipe_payload),
                        "source_key": prepared.source_key,
                        "source_hash": source_hash,
                    },
                    ensure_ascii=False,
                ),
            ),
        )


def _load_existing_recipes(connection) -> Dict[str, Dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            id,
            COALESCE(NULLIF(TRIM(source_key), ''), NULLIF(TRIM(name), '')) AS effective_source_key,
            source_hash
        FROM recipes
        ORDER BY id DESC
        """
    ).fetchall()

    existing: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        source_key = row["effective_source_key"]
        if not source_key or source_key in existing:
            continue
        existing[source_key] = {
            "id": row["id"],
            "source_hash": row["source_hash"],
        }

    return existing


def _deduplicate_existing_recipes(connection) -> None:
    rows = connection.execute(
        """
        SELECT
            id,
            COALESCE(NULLIF(TRIM(source_key), ''), NULLIF(TRIM(name), '')) AS effective_source_key
        FROM recipes
        ORDER BY id DESC
        """
    ).fetchall()

    seen = set()
    duplicate_ids = []
    for row in rows:
        key = row["effective_source_key"]
        if not key:
            continue
        if key in seen:
            duplicate_ids.append(row["id"])
            continue
        seen.add(key)

    if not duplicate_ids:
        return

    placeholders = ", ".join("?" for _ in duplicate_ids)
    connection.execute(f"DELETE FROM recipes WHERE id IN ({placeholders})", duplicate_ids)


def _insert_recipe(connection, recipe_payload: Dict[str, Any], source_key: str, source_hash: str, batch_id: int) -> int:
    cursor = connection.execute(
        """
        INSERT INTO recipes (
            name,
            record_kind,
            backlog_status,
            source_key,
            source_hash,
            last_import_batch_id,
            alias,
            library_section,
            section_name,
            category,
            cuisine,
            sub_cuisine,
            flavor,
            difficulty,
            estimated_time,
            servings,
            tools,
            ingredients_text,
            seasonings_text,
            steps_text,
            notes_text,
            source_reference,
            last_reviewed_on,
            bmd_flag,
            cc_flag,
            source_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_payload["name"],
            recipe_payload["record_kind"],
            recipe_payload["backlog_status"],
            source_key,
            source_hash,
            batch_id,
            recipe_payload["alias"],
            recipe_payload["library_section"],
            recipe_payload["section_name"],
            recipe_payload["category"],
            recipe_payload["cuisine"],
            recipe_payload["sub_cuisine"],
            recipe_payload["flavor"],
            recipe_payload["difficulty"],
            recipe_payload["estimated_time"],
            recipe_payload["servings"],
            recipe_payload["tools"],
            recipe_payload["ingredients_text"],
            recipe_payload["seasonings_text"],
            recipe_payload["steps_text"],
            recipe_payload["notes_text"],
            recipe_payload["source_reference"],
            recipe_payload["last_reviewed_on"],
            recipe_payload["bmd_flag"],
            recipe_payload["cc_flag"],
            recipe_payload["source_text"],
        ),
    )
    return cursor.lastrowid


def _update_recipe(connection, recipe_id: int, recipe_payload: Dict[str, Any], source_key: str, source_hash: str, batch_id: int) -> None:
    connection.execute(
        """
        UPDATE recipes
        SET
            name = ?,
            record_kind = ?,
            backlog_status = ?,
            source_key = ?,
            source_hash = ?,
            last_import_batch_id = ?,
            alias = ?,
            library_section = ?,
            section_name = ?,
            category = ?,
            cuisine = ?,
            sub_cuisine = ?,
            flavor = ?,
            difficulty = ?,
            estimated_time = ?,
            servings = ?,
            tools = ?,
            ingredients_text = ?,
            seasonings_text = ?,
            steps_text = ?,
            notes_text = ?,
            source_reference = ?,
            last_reviewed_on = ?,
            bmd_flag = ?,
            cc_flag = ?,
            source_text = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            recipe_payload["name"],
            recipe_payload["record_kind"],
            recipe_payload["backlog_status"],
            source_key,
            source_hash,
            batch_id,
            recipe_payload["alias"],
            recipe_payload["library_section"],
            recipe_payload["section_name"],
            recipe_payload["category"],
            recipe_payload["cuisine"],
            recipe_payload["sub_cuisine"],
            recipe_payload["flavor"],
            recipe_payload["difficulty"],
            recipe_payload["estimated_time"],
            recipe_payload["servings"],
            recipe_payload["tools"],
            recipe_payload["ingredients_text"],
            recipe_payload["seasonings_text"],
            recipe_payload["steps_text"],
            recipe_payload["notes_text"],
            recipe_payload["source_reference"],
            recipe_payload["last_reviewed_on"],
            recipe_payload["bmd_flag"],
            recipe_payload["cc_flag"],
            recipe_payload["source_text"],
            recipe_id,
        ),
    )


def _replace_recipe_tags(connection, recipe_id: int, tags: List[str]) -> None:
    connection.execute("DELETE FROM recipe_tags WHERE recipe_id = ?", (recipe_id,))

    tag_cache = _load_tag_cache(connection)
    for tag_name in tags:
        tag_id = _get_or_create_tag(connection, tag_cache, tag_name)
        connection.execute(
            """
            INSERT INTO recipe_tags (recipe_id, tag_id)
            VALUES (?, ?)
            """,
            (recipe_id, tag_id),
        )


def _build_mapped_row(recipe_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "record_kind": "待办事项" if recipe_payload["record_kind"] == "backlog" else "正式菜谱",
        "name": recipe_payload["name"],
        "library_section": recipe_payload["library_section"],
        "section_name": recipe_payload["section_name"],
        "cuisine": recipe_payload["cuisine"],
        "sub_cuisine": recipe_payload["sub_cuisine"],
        "bmd_flag": "是" if recipe_payload["bmd_flag"] else "",
        "cc_flag": "是" if recipe_payload["cc_flag"] else "",
        "last_reviewed_on": recipe_payload["last_reviewed_on"],
        "source_reference": recipe_payload["source_reference"],
        "ingredients_text": recipe_payload["ingredients_text"],
        "seasonings_text": recipe_payload["seasonings_text"],
        "steps_text": recipe_payload["steps_text"],
        "notes_text": recipe_payload["notes_text"],
    }


def _build_source_hash(recipe_payload: Dict[str, Any]) -> str:
    serialized = json.dumps(recipe_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_tag_cache(connection) -> Dict[str, int]:
    rows = connection.execute("SELECT id, name FROM tags").fetchall()
    return {row["name"]: row["id"] for row in rows}


def _get_or_create_tag(connection, tag_cache: Dict[str, int], tag_name: str) -> int:
    existing_id = tag_cache.get(tag_name)
    if existing_id is not None:
        return existing_id

    cursor = connection.execute(
        """
        INSERT INTO tags (name)
        VALUES (?)
        """,
        (tag_name,),
    )
    tag_id = cursor.lastrowid
    tag_cache[tag_name] = tag_id
    return tag_id


def _delete_unused_tags(connection) -> None:
    connection.execute(
        """
        DELETE FROM tags
        WHERE id NOT IN (
            SELECT DISTINCT tag_id
            FROM recipe_tags
        )
        """
    )


def _delete_unused_ingredients(connection) -> None:
    connection.execute(
        """
        DELETE FROM ingredients
        WHERE id NOT IN (
            SELECT DISTINCT ingredient_id
            FROM recipe_ingredients
        )
        """
    )


def _safe_json_loads(raw_value: Optional[str]) -> Dict[str, Any]:
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}
