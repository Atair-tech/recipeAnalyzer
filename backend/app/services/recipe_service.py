import json
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import DATABASE_PATH
from app.db.database import get_connection


def list_recipes(
    search: Optional[str] = None,
    status: Optional[str] = None,
    library_section: Optional[str] = None,
    section_name: Optional[str] = None,
    cuisine: Optional[str] = None,
    ingredient: Optional[str] = None,
    tag: Optional[str] = None,
    managed_tags: Optional[List[str]] = None,
    bmd_only: bool = False,
    cc_only: bool = False,
) -> List[Dict[str, Any]]:
    rows = _query_recipe_rows(
        search=search,
        status=status,
        library_section=library_section,
        section_name=section_name,
        cuisine=cuisine,
        ingredient=ingredient,
        tag=tag,
        managed_tags=managed_tags,
        bmd_only=bmd_only,
        cc_only=cc_only,
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "id": row["id"],
                "name": row["name"],
                "record_kind": row["record_kind"],
                "backlog_status": row["backlog_status"],
                "alias": row["alias"],
                "library_section": row["library_section"],
                "section_name": row["section_name"],
                "cuisine": row["cuisine"],
                "sub_cuisine": row["sub_cuisine"],
                "source_reference": row["source_reference"],
                "last_reviewed_on": row["last_reviewed_on"],
                "bmd_flag": bool(row["bmd_flag"]),
                "cc_flag": bool(row["cc_flag"]),
                "updated_at": row["updated_at"],
                "tags": row["tag_names"].split(",") if row["tag_names"] else [],
                "managed_tags": row["managed_tag_names"].split(",") if row["managed_tag_names"] else [],
            }
        )

    return items


def export_recipes_rows(
    search: Optional[str] = None,
    status: Optional[str] = None,
    library_section: Optional[str] = None,
    section_name: Optional[str] = None,
    cuisine: Optional[str] = None,
    ingredient: Optional[str] = None,
    tag: Optional[str] = None,
    managed_tags: Optional[List[str]] = None,
    bmd_only: bool = False,
    cc_only: bool = False,
) -> List[Dict[str, Any]]:
    rows = _query_recipe_rows(
        search=search,
        status=status,
        library_section=library_section,
        section_name=section_name,
        cuisine=cuisine,
        ingredient=ingredient,
        tag=tag,
        managed_tags=managed_tags,
        bmd_only=bmd_only,
        cc_only=cc_only,
        include_export_fields=True,
    )

    export_rows: List[Dict[str, Any]] = []
    for row in rows:
        export_rows.append(
            {
                "菜名": row["name"],
                "记录类型": row["backlog_status"] if row["record_kind"] == "backlog" else "正式菜谱",
                "专题库": row["library_section"] or "",
                "分组": row["section_name"] or "",
                "菜系": row["cuisine"] or "",
                "亚菜系": row["sub_cuisine"] or "",
                "标签": row["tag_names"] or "",
                "自动标签": row["managed_tag_names"] or "",
                "食材": row["ingredients_text"] or "",
                "调料": row["seasonings_text"] or "",
                "做法及要点": row["steps_text"] or "",
                "系统备注": row["notes_text"] or "",
                "来源/修订备注": row["source_reference"] or "",
                "最后记录日期": row["last_reviewed_on"] or "",
                "BMD": "是" if row["bmd_flag"] else "",
                "CC": "是" if row["cc_flag"] else "",
            }
        )
    return export_rows


def get_recipe_filters() -> Dict[str, Any]:
    with get_connection() as connection:
        library_section_rows = connection.execute(
            """
            SELECT DISTINCT library_section
            FROM recipes
            WHERE record_kind = 'recipe'
              AND library_section IS NOT NULL
              AND TRIM(library_section) <> ''
            ORDER BY library_section
            """
        ).fetchall()
        section_rows = connection.execute(
            """
            SELECT DISTINCT section_name
            FROM recipes
            WHERE record_kind = 'recipe'
              AND section_name IS NOT NULL
              AND TRIM(section_name) <> ''
            ORDER BY section_name
            """
        ).fetchall()
        cuisine_rows = connection.execute(
            """
            SELECT DISTINCT cuisine
            FROM recipes
            WHERE cuisine IS NOT NULL AND TRIM(cuisine) <> ''
            ORDER BY cuisine
            """
        ).fetchall()
        ingredient_rows = connection.execute(
            """
            SELECT DISTINCT COALESCE(i.normalized_name, i.name) AS ingredient_name
            FROM recipe_ingredients AS ri
            INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
            WHERE COALESCE(i.normalized_name, i.name) IS NOT NULL
              AND TRIM(COALESCE(i.normalized_name, i.name)) <> ''
            ORDER BY ingredient_name
            """
        ).fetchall()
        tag_rows = connection.execute(
            """
            SELECT DISTINCT name
            FROM tags
            WHERE name IS NOT NULL AND TRIM(name) <> ''
            ORDER BY name
            """
        ).fetchall()
        managed_tag_rows = connection.execute(
            """
            SELECT DISTINCT name
            FROM managed_tags
            WHERE is_active = 1
              AND name IS NOT NULL
              AND TRIM(name) <> ''
            ORDER BY sort_order, id
            """
        ).fetchall()
        section_relation_rows = connection.execute(
            """
            SELECT DISTINCT library_section, section_name
            FROM recipes
            WHERE record_kind = 'recipe'
              AND library_section IS NOT NULL
              AND TRIM(library_section) <> ''
              AND section_name IS NOT NULL
              AND TRIM(section_name) <> ''
            ORDER BY library_section, section_name
            """
        ).fetchall()

    section_names_by_library_section: Dict[str, List[str]] = {}
    library_sections_by_section_name: Dict[str, List[str]] = {}
    for row in section_relation_rows:
        library_section = row["library_section"]
        section_name = row["section_name"]
        section_names_by_library_section.setdefault(library_section, []).append(section_name)
        library_sections_by_section_name.setdefault(section_name, []).append(library_section)

    section_names_by_library_section = {
        key: sorted(set(values))
        for key, values in section_names_by_library_section.items()
    }
    library_sections_by_section_name = {
        key: sorted(set(values))
        for key, values in library_sections_by_section_name.items()
    }

    return {
        "statuses": ["recipe", "待挑战", "待记录"],
        "library_sections": [row["library_section"] for row in library_section_rows],
        "section_names": [row["section_name"] for row in section_rows],
        "cuisines": [row["cuisine"] for row in cuisine_rows],
        "ingredients": [row["ingredient_name"] for row in ingredient_rows],
        "tags": [row["name"] for row in tag_rows],
        "managed_tags": [row["name"] for row in managed_tag_rows],
        "section_names_by_library_section": section_names_by_library_section,
        "library_sections_by_section_name": library_sections_by_section_name,
    }


def get_recipe(recipe_id: int) -> Optional[Dict[str, Any]]:
    recipe_query = """
        SELECT
            id,
            name,
            record_kind,
            backlog_status,
            alias,
            source_key,
            last_import_batch_id,
            library_section,
            section_name,
            category,
            cuisine,
            sub_cuisine,
            source_reference,
            last_reviewed_on,
            bmd_flag,
            cc_flag,
            flavor,
            difficulty,
            estimated_time,
            servings,
            tools,
            ingredients_text,
            seasonings_text,
            steps_text,
            notes_text,
            source_text,
            created_at,
            updated_at
        FROM recipes
        WHERE id = ?
    """

    ingredients_query = """
        SELECT
            i.name,
            ri.amount,
            ri.unit,
            ri.remark
        FROM recipe_ingredients AS ri
        INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
        WHERE ri.recipe_id = ?
        ORDER BY ri.id
    """

    tags_query = """
        SELECT t.name
        FROM recipe_tags AS rt
        INNER JOIN tags AS t ON t.id = rt.tag_id
        WHERE rt.recipe_id = ?
        ORDER BY t.name
    """

    managed_tags_query = """
        SELECT
            mt.name,
            rmt.confidence,
            rmt.reason,
            rmt.source
        FROM recipe_managed_tags AS rmt
        INNER JOIN managed_tags AS mt ON mt.id = rmt.managed_tag_id
        WHERE rmt.recipe_id = ?
        ORDER BY mt.sort_order, mt.id
    """

    with get_connection() as connection:
        recipe_row = connection.execute(recipe_query, (recipe_id,)).fetchone()
        if recipe_row is None:
            return None

        ingredient_rows = connection.execute(ingredients_query, (recipe_id,)).fetchall()
        tag_rows = connection.execute(tags_query, (recipe_id,)).fetchall()
        managed_tag_rows = connection.execute(managed_tags_query, (recipe_id,)).fetchall()
        original_source_text = _load_original_source_text(
            connection=connection,
            batch_id=recipe_row["last_import_batch_id"],
            source_key=recipe_row["source_key"],
        )

    return {
        "id": recipe_row["id"],
        "name": recipe_row["name"],
        "record_kind": recipe_row["record_kind"],
        "backlog_status": recipe_row["backlog_status"],
        "alias": recipe_row["alias"],
        "library_section": recipe_row["library_section"],
        "section_name": recipe_row["section_name"],
        "category": recipe_row["category"],
        "cuisine": recipe_row["cuisine"],
        "sub_cuisine": recipe_row["sub_cuisine"],
        "source_reference": recipe_row["source_reference"],
        "last_reviewed_on": recipe_row["last_reviewed_on"],
        "bmd_flag": bool(recipe_row["bmd_flag"]),
        "cc_flag": bool(recipe_row["cc_flag"]),
        "flavor": recipe_row["flavor"],
        "difficulty": recipe_row["difficulty"],
        "estimated_time": recipe_row["estimated_time"],
        "servings": recipe_row["servings"],
        "tools": recipe_row["tools"],
        "ingredients_text": recipe_row["ingredients_text"],
        "seasonings_text": recipe_row["seasonings_text"],
        "steps_text": recipe_row["steps_text"],
        "notes_text": recipe_row["notes_text"],
        "source_text": recipe_row["source_text"],
        "original_source_text": original_source_text,
        "created_at": recipe_row["created_at"],
        "updated_at": recipe_row["updated_at"],
        "tags": [row["name"] for row in tag_rows],
        "managed_tags": [
            {
                "name": row["name"],
                "confidence": row["confidence"],
                "reason": row["reason"],
                "source": row["source"],
            }
            for row in managed_tag_rows
        ],
        "ingredients": [
            {
                "name": row["name"],
                "amount": row["amount"],
                "unit": row["unit"],
                "remark": row["remark"],
            }
            for row in ingredient_rows
        ],
    }


def get_overview() -> Dict[str, Any]:
    with get_connection() as connection:
        overview_row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN record_kind = 'recipe' THEN 1 ELSE 0 END) AS recipe_count,
                SUM(CASE WHEN record_kind = 'backlog' THEN 1 ELSE 0 END) AS backlog_count,
                COUNT(DISTINCT library_section) AS library_section_count,
                COUNT(*) AS total_record_count
            FROM recipes
            """
        ).fetchone()
        import_batch_count = connection.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        latest_recipe = connection.execute(
            """
            SELECT name, updated_at
            FROM recipes
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    return {
        "recipe_count": overview_row["recipe_count"] or 0,
        "backlog_count": overview_row["backlog_count"] or 0,
        "library_section_count": overview_row["library_section_count"] or 0,
        "total_record_count": overview_row["total_record_count"] or 0,
        "import_batch_count": import_batch_count,
        "latest_recipe_name": latest_recipe["name"] if latest_recipe else None,
        "latest_updated_at": latest_recipe["updated_at"] if latest_recipe else None,
        "database_path": str(DATABASE_PATH),
    }


def _query_recipe_rows(
    search: Optional[str] = None,
    status: Optional[str] = None,
    library_section: Optional[str] = None,
    section_name: Optional[str] = None,
    cuisine: Optional[str] = None,
    ingredient: Optional[str] = None,
    tag: Optional[str] = None,
    managed_tags: Optional[List[str]] = None,
    bmd_only: bool = False,
    cc_only: bool = False,
    include_export_fields: bool = False,
):
    where_sql, params = _build_recipe_filters(
        search=search,
        status=status,
        library_section=library_section,
        section_name=section_name,
        cuisine=cuisine,
        ingredient=ingredient,
        tag=tag,
        managed_tags=managed_tags,
        bmd_only=bmd_only,
        cc_only=cc_only,
    )

    extra_fields = ""
    if include_export_fields:
        extra_fields = """
            ,
            r.ingredients_text,
            r.seasonings_text,
            r.steps_text,
            r.notes_text
        """

    query = f"""
        SELECT
            r.id,
            r.name,
            r.record_kind,
            r.backlog_status,
            r.alias,
            r.library_section,
            r.section_name,
            r.cuisine,
            r.sub_cuisine,
            r.source_reference,
            r.last_reviewed_on,
            r.bmd_flag,
            r.cc_flag,
            r.updated_at,
            GROUP_CONCAT(DISTINCT t.name) AS tag_names,
            GROUP_CONCAT(DISTINCT mt.name) AS managed_tag_names
            {extra_fields}
        FROM recipes AS r
        LEFT JOIN recipe_tags AS rt ON rt.recipe_id = r.id
        LEFT JOIN tags AS t ON t.id = rt.tag_id
        LEFT JOIN recipe_managed_tags AS rmt ON rmt.recipe_id = r.id
        LEFT JOIN managed_tags AS mt ON mt.id = rmt.managed_tag_id
        {where_sql}
        GROUP BY r.id
        ORDER BY
            CASE WHEN r.record_kind = 'recipe' THEN 0 ELSE 1 END,
            COALESCE(r.library_section, ''),
            COALESCE(r.section_name, ''),
            r.name
    """

    with get_connection() as connection:
        return connection.execute(query, params).fetchall()


def _build_recipe_filters(
    search: Optional[str] = None,
    status: Optional[str] = None,
    library_section: Optional[str] = None,
    section_name: Optional[str] = None,
    cuisine: Optional[str] = None,
    ingredient: Optional[str] = None,
    tag: Optional[str] = None,
    managed_tags: Optional[List[str]] = None,
    bmd_only: bool = False,
    cc_only: bool = False,
) -> Tuple[str, List[Any]]:
    where_clauses = []
    params: List[Any] = []

    if search:
        search_term = f"%{search.strip()}%"
        where_clauses.append(
            "("
            "r.name LIKE ? OR "
            "COALESCE(r.alias, '') LIKE ? OR "
            "COALESCE(r.library_section, '') LIKE ? OR "
            "COALESCE(r.section_name, '') LIKE ? OR "
            "COALESCE(r.cuisine, '') LIKE ? OR "
            "COALESCE(r.sub_cuisine, '') LIKE ? OR "
            "COALESCE(r.ingredients_text, '') LIKE ? OR "
            "COALESCE(r.seasonings_text, '') LIKE ? OR "
            "COALESCE(r.steps_text, '') LIKE ? OR "
            "COALESCE(r.notes_text, '') LIKE ?"
            ")"
        )
        params.extend([search_term] * 10)

    if status == "recipe":
        where_clauses.append("r.record_kind = 'recipe'")
    elif status in {"待挑战", "待记录"}:
        where_clauses.append("r.record_kind = 'backlog' AND r.backlog_status = ?")
        params.append(status)

    if library_section:
        where_clauses.append("COALESCE(r.library_section, '') = ?")
        params.append(library_section.strip())

    if section_name:
        where_clauses.append("COALESCE(r.section_name, '') = ?")
        params.append(section_name.strip())

    if cuisine:
        where_clauses.append("COALESCE(r.cuisine, '') = ?")
        params.append(cuisine.strip())

    if ingredient:
        normalized_ingredient = ingredient.strip()
        where_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM recipe_ingredients AS filter_ri
                INNER JOIN ingredients AS filter_i ON filter_i.id = filter_ri.ingredient_id
                WHERE filter_ri.recipe_id = r.id
                  AND (
                    filter_i.normalized_name = ?
                    OR filter_i.name = ?
                    OR COALESCE(filter_i.alias, '') = ?
                  )
            )
            """
        )
        params.extend([normalized_ingredient, normalized_ingredient, normalized_ingredient])

    if tag:
        normalized_tag = tag.strip()
        where_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM recipe_tags AS filter_rt
                INNER JOIN tags AS filter_t ON filter_t.id = filter_rt.tag_id
                WHERE filter_rt.recipe_id = r.id
                  AND filter_t.name = ?
            )
            """
        )
        params.append(normalized_tag)

    normalized_managed_tags = sorted({item.strip() for item in (managed_tags or []) if item and item.strip()})
    if normalized_managed_tags:
        placeholders = ", ".join("?" for _ in normalized_managed_tags)
        where_clauses.append(
            f"""
            (
                SELECT COUNT(DISTINCT filter_mt.name)
                FROM recipe_managed_tags AS filter_rmt
                INNER JOIN managed_tags AS filter_mt ON filter_mt.id = filter_rmt.managed_tag_id
                WHERE filter_rmt.recipe_id = r.id
                  AND filter_mt.name IN ({placeholders})
            ) = ?
            """
        )
        params.extend(normalized_managed_tags)
        params.append(len(normalized_managed_tags))

    if bmd_only:
        where_clauses.append("r.bmd_flag = 1")

    if cc_only:
        where_clauses.append("r.cc_flag = 1")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return where_sql, params


def _load_original_source_text(connection, batch_id: Optional[int], source_key: Optional[str]) -> Optional[str]:
    if not batch_id or not source_key:
        return None

    rows = connection.execute(
        """
        SELECT raw_json, parse_result_json
        FROM raw_import_rows
        WHERE batch_id = ?
        """
        ,
        (batch_id,),
    ).fetchall()

    for row in rows:
        parse_result = _safe_json_loads(row["parse_result_json"])
        if parse_result.get("source_key") != source_key:
            continue

        raw_payload = _safe_json_loads(row["raw_json"])
        return _format_original_source_payload(raw_payload)

    return None


def _format_original_source_payload(payload: Dict[str, Any]) -> Optional[str]:
    if not payload:
        return None

    blocks: List[str] = []
    if payload.get("index_sheet") and payload.get("index_row"):
        blocks.append(_format_raw_row_block("索引页原始内容", payload.get("index_sheet"), payload.get("index_row_number"), payload["index_row"]))
    if payload.get("detail_sheet") and payload.get("detail_row"):
        blocks.append(_format_raw_row_block("做法页原始内容", payload.get("detail_sheet"), payload.get("detail_row_number"), payload["detail_row"]))
    if payload.get("sheet") and payload.get("raw_row"):
        blocks.append(_format_raw_row_block("原始内容", payload.get("sheet"), payload.get("row_number"), payload["raw_row"]))

    text = "\n\n".join(block for block in blocks if block)
    return text or None


def _format_raw_row_block(title: str, sheet_name: Optional[str], row_number: Optional[int], row_data: Dict[str, Any]) -> str:
    lines = [title]
    if sheet_name:
        lines.append(f"工作表: {sheet_name}")
    if row_number:
        lines.append(f"行号: {row_number}")

    cell_items = []
    for key in sorted(row_data):
        if key == "_row_number":
            continue
        value = row_data.get(key)
        if value in (None, ""):
            continue
        cell_items.append(f"{key}={value}")

    if cell_items:
        lines.append("单元格: " + " | ".join(cell_items))

    return "\n".join(lines)


def _safe_json_loads(raw_value: Optional[str]) -> Dict[str, Any]:
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}
