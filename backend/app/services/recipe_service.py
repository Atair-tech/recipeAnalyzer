import json
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import DATABASE_PATH
from app.db.database import get_connection
from app.services.search_service import rebuild_recipe_search_index


RECIPE_EDITOR_FIELDS = [
    {"key": "id", "label": "ID", "type": "readonly", "editable": False, "required": False},
    {"key": "name", "label": "菜名", "type": "text", "editable": True, "required": True},
    {"key": "record_kind", "label": "记录类型", "type": "select", "editable": True, "required": True},
    {"key": "backlog_status", "label": "待办状态", "type": "select", "editable": True, "required": False},
    {"key": "library_section", "label": "专题库", "type": "select", "editable": True, "required": False},
    {"key": "section_name", "label": "分组", "type": "select", "editable": True, "required": False},
    {"key": "category", "label": "分类", "type": "select", "editable": True, "required": False},
    {"key": "cuisine", "label": "大地域", "type": "select", "editable": True, "required": False},
    {"key": "sub_cuisine", "label": "小地域", "type": "select", "editable": True, "required": False},
    {"key": "ingredients_text", "label": "原始食材", "type": "longtext", "editable": True, "required": False},
    {"key": "seasonings_text", "label": "原始调料", "type": "longtext", "editable": True, "required": False},
    {"key": "steps_text", "label": "做法及要点", "type": "longtext", "editable": True, "required": False},
    {"key": "notes_text", "label": "系统备注", "type": "longtext", "editable": True, "required": False},
    {"key": "source_reference", "label": "来源/修订备注", "type": "text", "editable": True, "required": False},
    {"key": "last_reviewed_on", "label": "最后记录日期", "type": "text", "editable": True, "required": False},
    {"key": "bmd_flag", "label": "BMD", "type": "boolean", "editable": True, "required": False},
    {"key": "cc_flag", "label": "CC", "type": "boolean", "editable": True, "required": False},
    {"key": "source_text", "label": "源文本", "type": "longtext", "editable": True, "required": False},
    {"key": "source_key", "label": "导入源键", "type": "readonly", "editable": False, "required": False},
    {"key": "source_hash", "label": "导入源哈希", "type": "readonly", "editable": False, "required": False},
    {"key": "last_import_batch_id", "label": "导入批次", "type": "readonly", "editable": False, "required": False},
    {"key": "created_at", "label": "创建时间", "type": "readonly", "editable": False, "required": False},
    {"key": "updated_at", "label": "更新时间", "type": "readonly", "editable": False, "required": False},
    {"key": "tags_text", "label": "标签", "type": "text", "editable": True, "required": False},
    {"key": "managed_tags_text", "label": "自动标签(参考)", "type": "readonly", "editable": False, "required": False},
    {"key": "ingredient_names", "label": "主料/标准食材(参考)", "type": "readonly", "editable": False, "required": False},
]

EDITABLE_RECIPE_COLUMNS = {
    "name",
    "record_kind",
    "backlog_status",
    "library_section",
    "section_name",
    "category",
    "cuisine",
    "sub_cuisine",
    "ingredients_text",
    "seasonings_text",
    "steps_text",
    "notes_text",
    "source_reference",
    "last_reviewed_on",
    "bmd_flag",
    "cc_flag",
    "source_text",
}

REGION_SUB_CUISINE_OPTIONS = [
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
    "台湾",
    "日本",
    "韩国",
    "朝鲜",
    "越南",
    "泰国",
    "马来西亚",
    "新加坡",
    "印度尼西亚",
    "菲律宾",
    "印度",
    "土耳其",
    "意大利",
    "法国",
    "西班牙",
    "葡萄牙",
    "英国",
    "德国",
    "希腊",
    "俄罗斯",
    "美国",
    "加拿大",
    "墨西哥",
    "巴西",
    "秘鲁",
    "阿根廷",
    "澳大利亚",
    "新西兰",
    "摩洛哥",
    "埃及",
    "南非",
    "埃塞俄比亚",
    "中东",
    "地中海",
    "北欧",
    "东南亚",
    "南亚",
    "拉丁美洲",
]


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
            WHERE i.is_visible = 1
              AND COALESCE(i.normalized_name, i.name) IS NOT NULL
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


def get_recipe_editor_schema() -> Dict[str, Any]:
    option_fields = [
        "record_kind",
        "backlog_status",
        "library_section",
        "section_name",
        "category",
        "cuisine",
        "sub_cuisine",
        "tags_text",
        "managed_tags_text",
        "ingredient_names",
    ]
    options: Dict[str, List[str]] = {
        "record_kind": ["recipe", "backlog"],
        "backlog_status": ["待挑战", "待记录"],
    }

    with get_connection() as connection:
        for field_name in option_fields:
            if field_name in {"record_kind", "backlog_status", "tags_text", "managed_tags_text", "ingredient_names"}:
                continue
            if field_name == "sub_cuisine":
                options[field_name] = REGION_SUB_CUISINE_OPTIONS
                continue
            rows = connection.execute(
                f"""
                SELECT DISTINCT {field_name} AS value
                FROM recipes
                WHERE {field_name} IS NOT NULL AND TRIM({field_name}) <> ''
                ORDER BY {field_name}
                """
            ).fetchall()
            options[field_name] = [row["value"] for row in rows]

        tag_rows = connection.execute(
            """
            SELECT DISTINCT name AS value
            FROM tags
            WHERE name IS NOT NULL AND TRIM(name) <> ''
            ORDER BY name
            """
        ).fetchall()
        managed_tag_rows = connection.execute(
            """
            SELECT DISTINCT name AS value
            FROM managed_tags
            WHERE name IS NOT NULL AND TRIM(name) <> ''
            ORDER BY sort_order, id
            """
        ).fetchall()
        ingredient_rows = connection.execute(
            """
            SELECT DISTINCT COALESCE(normalized_name, name) AS value
            FROM ingredients
            WHERE is_visible = 1
              AND COALESCE(normalized_name, name) IS NOT NULL
              AND TRIM(COALESCE(normalized_name, name)) <> ''
            ORDER BY value
            """
        ).fetchall()

    options["tags_text"] = [row["value"] for row in tag_rows]
    options["managed_tags_text"] = [row["value"] for row in managed_tag_rows]
    options["ingredient_names"] = [row["value"] for row in ingredient_rows]

    return {
        "fields": RECIPE_EDITOR_FIELDS,
        "default_filters": ["ingredient_names", "cuisine", "sub_cuisine", "record_kind", "library_section"],
        "options": options,
    }


def list_recipe_editor_rows() -> List[Dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                r.id,
                r.name,
                r.record_kind,
                r.backlog_status,
                r.source_key,
                r.source_hash,
                r.last_import_batch_id,
                r.library_section,
                r.section_name,
                r.category,
                r.cuisine,
                r.sub_cuisine,
                r.ingredients_text,
                r.seasonings_text,
                r.steps_text,
                r.notes_text,
                r.source_reference,
                r.last_reviewed_on,
                r.bmd_flag,
                r.cc_flag,
                r.source_text,
                r.created_at,
                r.updated_at,
                GROUP_CONCAT(DISTINCT t.name) AS tags_text,
                GROUP_CONCAT(DISTINCT mt.name) AS managed_tags_text,
                GROUP_CONCAT(DISTINCT COALESCE(i.normalized_name, i.name)) AS ingredient_names
            FROM recipes AS r
            LEFT JOIN recipe_tags AS rt ON rt.recipe_id = r.id
            LEFT JOIN tags AS t ON t.id = rt.tag_id
            LEFT JOIN recipe_managed_tags AS rmt ON rmt.recipe_id = r.id
            LEFT JOIN managed_tags AS mt ON mt.id = rmt.managed_tag_id
            LEFT JOIN recipe_ingredients AS ri ON ri.recipe_id = r.id
            LEFT JOIN ingredients AS i ON i.id = ri.ingredient_id AND i.is_visible = 1
            GROUP BY r.id
            ORDER BY
                CASE WHEN r.record_kind = 'recipe' THEN 0 ELSE 1 END,
                COALESCE(r.library_section, ''),
                COALESCE(r.section_name, ''),
                r.name
            """
        ).fetchall()

    return [_format_editor_row(row) for row in rows]


def create_recipe_editor_row(values: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = _normalize_editor_values(values)
    name = cleaned.get("name")
    if not name:
        raise ValueError("菜名不能为空")

    insert_columns = [column for column in EDITABLE_RECIPE_COLUMNS if column in cleaned]
    if "name" not in insert_columns:
        insert_columns.append("name")
    if "record_kind" not in insert_columns:
        insert_columns.append("record_kind")
        cleaned["record_kind"] = "recipe"

    placeholders = ", ".join("?" for _ in insert_columns)
    column_sql = ", ".join(insert_columns)

    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            INSERT INTO recipes ({column_sql})
            VALUES ({placeholders})
            """,
            [_coerce_db_value(column, cleaned.get(column)) for column in insert_columns],
        )
        recipe_id = cursor.lastrowid
        _replace_recipe_tags(connection, recipe_id, _parse_tag_values(cleaned.get("tags_text", "")))
        rebuild_recipe_search_index(connection)
        connection.commit()

    return get_recipe_editor_row(recipe_id)


def update_recipe_editor_row(recipe_id: int, values: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_recipe(recipe_id)
    if existing is None:
        return None

    cleaned = _normalize_editor_values(values)
    update_columns = [column for column in EDITABLE_RECIPE_COLUMNS if column in cleaned]

    with get_connection() as connection:
        if update_columns:
            set_sql = ", ".join(f"{column} = ?" for column in update_columns)
            params = [_coerce_db_value(column, cleaned.get(column)) for column in update_columns]
            params.append(recipe_id)
            connection.execute(
                f"""
                UPDATE recipes
                SET {set_sql},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                params,
            )

        if "tags_text" in cleaned or "tags" in cleaned:
            _replace_recipe_tags(connection, recipe_id, _parse_tag_values(cleaned.get("tags_text", cleaned.get("tags", ""))))

        rebuild_recipe_search_index(connection)
        connection.commit()

    return get_recipe_editor_row(recipe_id)


def update_recipe(recipe_id: int, payload: Any) -> Optional[Dict[str, Any]]:
    values = payload.model_dump()
    values["tags_text"] = "、".join(values.pop("tags", []))
    row = update_recipe_editor_row(recipe_id, values)
    return get_recipe(recipe_id) if row is not None else None


def get_recipe_editor_row(recipe_id: int) -> Dict[str, Any]:
    rows = [row for row in list_recipe_editor_rows() if row["id"] == recipe_id]
    if not rows:
        raise ValueError("Recipe not found")
    return rows[0]


def get_recipe(recipe_id: int) -> Optional[Dict[str, Any]]:
    recipe_query = """
        SELECT
            id,
            name,
            record_kind,
            backlog_status,
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
          AND i.is_visible = 1
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
        original_source_bundle = _load_original_source_bundle(
            connection=connection,
            batch_id=recipe_row["last_import_batch_id"],
            source_key=recipe_row["source_key"],
        )

    return {
        "id": recipe_row["id"],
        "name": recipe_row["name"],
        "record_kind": recipe_row["record_kind"],
        "backlog_status": recipe_row["backlog_status"],
        "library_section": recipe_row["library_section"],
        "section_name": recipe_row["section_name"],
        "category": recipe_row["category"],
        "cuisine": recipe_row["cuisine"],
        "sub_cuisine": recipe_row["sub_cuisine"],
        "source_reference": recipe_row["source_reference"],
        "last_reviewed_on": recipe_row["last_reviewed_on"],
        "bmd_flag": bool(recipe_row["bmd_flag"]),
        "cc_flag": bool(recipe_row["cc_flag"]),
        "ingredients_text": recipe_row["ingredients_text"],
        "seasonings_text": recipe_row["seasonings_text"],
        "steps_text": recipe_row["steps_text"],
        "notes_text": recipe_row["notes_text"],
        "source_text": recipe_row["source_text"],
        "original_source_text": original_source_bundle["original_source_text"],
        "original_sections": original_source_bundle["original_sections"],
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
        params.extend([search_term] * 9)

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
                  AND filter_i.is_visible = 1
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


def _load_original_source_bundle(connection, batch_id: Optional[int], source_key: Optional[str]) -> Dict[str, Any]:
    fallback_bundle = {
        "original_source_text": None,
        "original_sections": {
            "ingredients_text": None,
            "seasonings_text": None,
            "steps_text": None,
        },
    }

    if not batch_id or not source_key:
        return fallback_bundle

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
        return {
            "original_source_text": _format_original_source_payload(raw_payload),
            "original_sections": _extract_original_sections(raw_payload),
        }

    return fallback_bundle


def _format_editor_row(row) -> Dict[str, Any]:
    item = {field["key"]: row[field["key"]] if field["key"] in row.keys() else None for field in RECIPE_EDITOR_FIELDS}
    item["bmd_flag"] = bool(row["bmd_flag"])
    item["cc_flag"] = bool(row["cc_flag"])
    item["tags_text"] = row["tags_text"] or ""
    item["managed_tags_text"] = row["managed_tags_text"] or ""
    item["ingredient_names"] = row["ingredient_names"] or ""
    return item


def _normalize_editor_values(values: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in values.items():
        if key not in EDITABLE_RECIPE_COLUMNS and key not in {"tags_text", "tags"}:
            continue
        if isinstance(value, str):
            cleaned[key] = value.strip() or None
        else:
            cleaned[key] = value

    if not cleaned.get("record_kind"):
        cleaned["record_kind"] = "recipe"
    if cleaned.get("record_kind") not in {"recipe", "backlog"}:
        raise ValueError("记录类型只能是 recipe 或 backlog")
    if cleaned.get("record_kind") == "recipe":
        cleaned["backlog_status"] = None

    return cleaned


def _coerce_db_value(column: str, value: Any) -> Any:
    if column in {"bmd_flag", "cc_flag"}:
        return 1 if value else 0
    return value


def _parse_tag_values(raw_value: Any) -> List[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        candidates = raw_value
    else:
        text = str(raw_value)
        for separator in ("，", "、", ";", "；", "\n"):
            text = text.replace(separator, ",")
        candidates = text.split(",")

    cleaned: List[str] = []
    seen = set()
    for candidate in candidates:
        tag = str(candidate).strip()
        if tag and tag not in seen:
            seen.add(tag)
            cleaned.append(tag)
    return cleaned


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


def _extract_original_sections(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    detail_row = payload.get("detail_row") if isinstance(payload.get("detail_row"), dict) else {}
    raw_row = payload.get("raw_row") if isinstance(payload.get("raw_row"), dict) else {}

    if detail_row:
        return {
            "ingredients_text": _clean_nullable_text(detail_row.get("C")),
            "seasonings_text": _clean_nullable_text(detail_row.get("D")),
            "steps_text": _clean_nullable_text(detail_row.get("E")),
        }

    if raw_row:
        return {
            "ingredients_text": _clean_nullable_text(raw_row.get("C")),
            "seasonings_text": _clean_nullable_text(raw_row.get("D")),
            "steps_text": _clean_nullable_text(raw_row.get("E")),
        }

    return {
        "ingredients_text": None,
        "seasonings_text": None,
        "steps_text": None,
    }


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


def _clean_nullable_text(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or None
