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

TABLE_EDITOR_EXCLUDED_PREFIXES = ("recipe_search", "sqlite_")
TABLE_EDITOR_EXCLUDED_TABLES = {
    "recipe_search",
    "recipe_search_config",
    "recipe_search_content",
    "recipe_search_data",
    "recipe_search_docsize",
    "recipe_search_idx",
}

TABLE_EDITOR_LABELS = {
    "recipes": "recipes 菜谱主表",
    "ingredients": "ingredients 标准食材",
    "ingredient_aliases": "ingredient_aliases 食材别名",
    "recipe_ingredients": "recipe_ingredients 菜谱-食材",
    "managed_tags": "managed_tags 管理标签",
    "recipe_managed_tags": "recipe_managed_tags 菜谱-管理标签",
    "tags": "tags 旧标签",
    "recipe_tags": "recipe_tags 旧菜谱标签",
    "import_batches": "import_batches 导入批次",
    "raw_import_rows": "raw_import_rows 原始导入行",
    "ai_conversation_logs": "ai_conversation_logs AI日志",
    "ai_refine_runs": "ai_refine_runs 食材分析批次",
    "recipe_ai_refine_state": "recipe_ai_refine_state 食材分析状态",
    "recipe_refine_snapshots": "recipe_refine_snapshots 食材分析快照",
    "recipe_refine_reviews": "recipe_refine_reviews 食材审核",
    "ai_ingredient_filter_runs": "ai_ingredient_filter_runs 食材过滤批次",
    "ingredient_ai_filter_state": "ingredient_ai_filter_state 食材过滤状态",
    "ai_tagging_runs": "ai_tagging_runs 自动标签批次",
    "recipe_ai_tag_state": "recipe_ai_tag_state 自动标签状态",
    "recipe_pair_overrides": "recipe_pair_overrides 配对修正",
}

SQL_EDITOR_BLOCKED_PREFIXES = ("attach", "detach")

USER_VIEW_DEFINITIONS = {
    "recipes": {
        "label": "菜谱阅览",
        "description": "按用户阅览字段展示菜谱，包含原始 Excel 文本和参考标签/食材。",
        "order_by": '"记录类型", "主题", "分组", "菜名"',
        "columns": [
            {"name": "菜名", "type": "TEXT"},
            {"name": "主题", "type": "TEXT"},
            {"name": "分组", "type": "TEXT"},
            {"name": "大地域", "type": "TEXT"},
            {"name": "细分地域", "type": "TEXT"},
            {"name": "食材", "type": "TEXT"},
            {"name": "调料", "type": "TEXT"},
            {"name": "做法与要点", "type": "TEXT"},
            {"name": "来源/修订备注", "type": "TEXT"},
            {"name": "最后记录日期", "type": "TEXT"},
            {"name": "BMD", "type": "INTEGER"},
            {"name": "CC", "type": "INTEGER"},
            {"name": "自动标签（参考）", "type": "TEXT"},
            {"name": "标准食材（参考）", "type": "TEXT"},
            {"name": "记录类型", "type": "TEXT"},
            {"name": "待办状态", "type": "TEXT"},
        ],
        "sql": """
            SELECT
                r.name AS "菜名",
                COALESCE(r.library_section, '') AS "主题",
                COALESCE(r.section_name, '') AS "分组",
                COALESCE(r.cuisine, '') AS "大地域",
                COALESCE(r.sub_cuisine, '') AS "细分地域",
                COALESCE(r.ingredients_text, '') AS "食材",
                COALESCE(r.seasonings_text, '') AS "调料",
                COALESCE(r.steps_text, '') AS "做法与要点",
                COALESCE(r.source_reference, '') AS "来源/修订备注",
                COALESCE(r.last_reviewed_on, '') AS "最后记录日期",
                COALESCE(r.bmd_flag, 0) AS "BMD",
                COALESCE(r.cc_flag, 0) AS "CC",
                COALESCE(GROUP_CONCAT(DISTINCT mt.name), '') AS "自动标签（参考）",
                COALESCE(GROUP_CONCAT(DISTINCT i.normalized_name), '') AS "标准食材（参考）",
                CASE r.record_kind
                    WHEN 'recipe' THEN '正式菜谱'
                    WHEN 'backlog' THEN '待办条目'
                    ELSE COALESCE(r.record_kind, '')
                END AS "记录类型",
                COALESCE(r.backlog_status, '') AS "待办状态"
            FROM recipes AS r
            LEFT JOIN recipe_managed_tags AS rmt ON rmt.recipe_id = r.id
            LEFT JOIN managed_tags AS mt ON mt.id = rmt.managed_tag_id
            LEFT JOIN recipe_ingredients AS ri ON ri.recipe_id = r.id
            LEFT JOIN ingredients AS i ON i.id = ri.ingredient_id AND i.is_visible = 1
            GROUP BY r.id
        """,
    },
    "ingredients": {
        "label": "标准食材索引",
        "description": "按标准食材查看关联菜谱数量和已维护别名。",
        "order_by": '"关联菜谱数" DESC, "标准食材"',
        "columns": [
            {"name": "标准食材", "type": "TEXT"},
            {"name": "可见", "type": "INTEGER"},
            {"name": "关联菜谱数", "type": "INTEGER"},
            {"name": "别名", "type": "TEXT"},
        ],
        "sql": """
            SELECT
                i.normalized_name AS "标准食材",
                COALESCE(i.is_visible, 0) AS "可见",
                COUNT(DISTINCT ri.recipe_id) AS "关联菜谱数",
                COALESCE(GROUP_CONCAT(DISTINCT ia.alias_name), '') AS "别名"
            FROM ingredients AS i
            LEFT JOIN recipe_ingredients AS ri ON ri.ingredient_id = i.id
            LEFT JOIN ingredient_aliases AS ia ON ia.ingredient_id = i.id
            GROUP BY i.id
        """,
    },
    "managed_tags": {
        "label": "自动标签索引",
        "description": "按自动标签查看说明、可见性和关联菜谱数量。",
        "order_by": '"关联菜谱数" DESC, "标签"',
        "columns": [
            {"name": "标签", "type": "TEXT"},
            {"name": "说明", "type": "TEXT"},
            {"name": "可见", "type": "INTEGER"},
            {"name": "关联菜谱数", "type": "INTEGER"},
        ],
        "sql": """
            SELECT
                mt.name AS "标签",
                COALESCE(mt.description, '') AS "说明",
                COALESCE(mt.is_active, 0) AS "可见",
                COUNT(DISTINCT rmt.recipe_id) AS "关联菜谱数"
            FROM managed_tags AS mt
            LEFT JOIN recipe_managed_tags AS rmt ON rmt.managed_tag_id = mt.id
            GROUP BY mt.id
        """,
    },
}

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
            SELECT DISTINCT i.normalized_name AS ingredient_name
            FROM recipe_ingredients AS ri
            INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
            WHERE i.is_visible = 1
              AND i.normalized_name IS NOT NULL
              AND TRIM(i.normalized_name) <> ''
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
            SELECT DISTINCT normalized_name AS value
            FROM ingredients
            WHERE is_visible = 1
              AND normalized_name IS NOT NULL
              AND TRIM(normalized_name) <> ''
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
                GROUP_CONCAT(DISTINCT i.normalized_name) AS ingredient_names
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


def get_table_editor_schema() -> Dict[str, Any]:
    with get_connection() as connection:
        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        tables = []
        for row in table_rows:
            table_name = row["name"]
            if table_name in TABLE_EDITOR_EXCLUDED_TABLES or table_name.startswith(TABLE_EDITOR_EXCLUDED_PREFIXES):
                continue
            columns = _get_table_editor_columns(connection, table_name)
            if not columns:
                continue
            count = connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            tables.append(
                {
                    "name": table_name,
                    "label": TABLE_EDITOR_LABELS.get(table_name, table_name),
                    "row_count": count,
                    "columns": columns,
                }
            )

    return {
        "tables": tables,
        "default_table": "recipes" if any(table["name"] == "recipes" for table in tables) else (tables[0]["name"] if tables else ""),
    }


def list_table_editor_rows(table: str, filters: Dict[str, Any], limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    schema = get_table_editor_schema()
    table_map = {item["name"]: item for item in schema["tables"]}
    table_info = table_map.get(table)
    if table_info is None:
        raise ValueError("不支持浏览该表")

    columns = table_info["columns"]
    column_names = [column["name"] for column in columns]
    where_sql, params = _build_table_editor_filters(filters, column_names, list_match_mode="contains")
    order_sql = _build_table_editor_order(columns)
    safe_limit = max(1, min(int(limit or 100), 500))
    safe_offset = max(0, int(offset or 0))

    select_columns = ", ".join(f'"{column}"' for column in column_names)
    with get_connection() as connection:
        total = connection.execute(
            f'SELECT COUNT(*) FROM "{table}" {where_sql}',
            params,
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT {select_columns}
            FROM "{table}"
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        ).fetchall()

    return {
        "table": table,
        "columns": columns,
        "items": [_serialize_table_editor_row(row, column_names) for row in rows],
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
    }


def get_user_view_editor_schema() -> Dict[str, Any]:
    with get_connection() as connection:
        views = []
        for view_name, definition in USER_VIEW_DEFINITIONS.items():
            total = connection.execute(
                f'SELECT COUNT(*) FROM ({definition["sql"]}) AS user_view'
            ).fetchone()[0]
            views.append(
                {
                    "name": view_name,
                    "label": definition["label"],
                    "description": definition.get("description", ""),
                    "row_count": total,
                    "columns": definition["columns"],
                }
            )

    return {
        "views": views,
        "default_view": "recipes",
    }


def list_user_view_editor_rows(
    view: str,
    filters: Dict[str, Any],
    limit: int = 100,
    offset: int = 0,
    sort_column: Optional[str] = None,
    sort_direction: Optional[str] = None,
) -> Dict[str, Any]:
    definition = USER_VIEW_DEFINITIONS.get(view)
    if definition is None:
        raise ValueError("不支持阅览该视图")

    columns = definition["columns"]
    column_names = [column["name"] for column in columns]
    where_sql, params = _build_table_editor_filters(filters, column_names)
    safe_limit = max(1, min(int(limit or 100), 500))
    safe_offset = max(0, int(offset or 0))
    if sort_column:
        if sort_column not in column_names:
            raise ValueError("不支持按该字段排序")
        direction = "DESC" if str(sort_direction or "").lower() == "desc" else "ASC"
        sort_column_info = next((column for column in columns if column["name"] == sort_column), {})
        sort_type = str(sort_column_info.get("type") or "").upper()
        if "INT" in sort_type or "REAL" in sort_type or "NUM" in sort_type:
            order_sql = f'ORDER BY CAST("{sort_column}" AS REAL) {direction}, "{sort_column}" COLLATE NOCASE {direction}'
        else:
            order_sql = f'ORDER BY "{sort_column}" COLLATE NOCASE {direction}'
    else:
        order_sql = f'ORDER BY {definition["order_by"]}' if definition.get("order_by") else ""

    with get_connection() as connection:
        total = connection.execute(
            f'SELECT COUNT(*) FROM ({definition["sql"]}) AS user_view {where_sql}',
            params,
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT *
            FROM ({definition["sql"]}) AS user_view
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        ).fetchall()

    return {
        "view": view,
        "columns": columns,
        "items": [_serialize_table_editor_row(row, column_names) for row in rows],
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "sort_column": sort_column or "",
        "sort_direction": "desc" if str(sort_direction or "").lower() == "desc" else ("asc" if sort_column else ""),
    }


def list_user_view_filter_values(
    view: str,
    column: str,
    filters: Dict[str, Any],
    search: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    definition = USER_VIEW_DEFINITIONS.get(view)
    if definition is None:
        raise ValueError("不支持阅览该视图")

    column_names = [item["name"] for item in definition["columns"]]
    if column not in column_names:
        raise ValueError("不支持筛选该字段")

    other_filters = {key: value for key, value in (filters or {}).items() if key != column}
    where_sql, params = _build_table_editor_filters(other_filters, column_names)
    clauses = [where_sql[6:]] if where_sql.startswith("WHERE ") else []
    search_text = (search or "").strip()
    if search_text:
        clauses.append(f'CAST("{column}" AS TEXT) LIKE ?')
        params.append(f"%{search_text}%")

    final_where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit or 5000), 5000))

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT COALESCE(CAST("{column}" AS TEXT), '') AS value
            FROM ({definition["sql"]}) AS user_view
            {final_where_sql}
            ORDER BY value COLLATE NOCASE
            LIMIT ?
            """,
            [*params, safe_limit],
        ).fetchall()

    return {
        "view": view,
        "column": column,
        "values": [row["value"] for row in rows],
        "limit": safe_limit,
    }


def execute_table_editor_sql(sql: str) -> Dict[str, Any]:
    statement = (sql or "").strip()
    if not statement:
        raise ValueError("SQL 不能为空")

    lowered = statement.lstrip().lower()
    first_word = lowered.split(None, 1)[0].rstrip(";") if lowered else ""
    if first_word in SQL_EDITOR_BLOCKED_PREFIXES:
        raise ValueError("出于安全原因，编辑器不允许执行 ATTACH/DETACH")

    with get_connection() as connection:
        try:
            cursor = connection.execute(statement)
            if cursor.description:
                columns = [column[0] for column in cursor.description]
                rows = cursor.fetchmany(500)
                truncated = cursor.fetchone() is not None
                return {
                    "kind": "rows",
                    "columns": columns,
                    "items": [_serialize_sql_result_row(row, columns) for row in rows],
                    "row_count": len(rows),
                    "truncated": truncated,
                    "message": f"返回 {len(rows)} 行" + ("；结果超过 500 行，已截断" if truncated else ""),
                }

            connection.commit()
            affected = cursor.rowcount if cursor.rowcount is not None else -1
            return {
                "kind": "message",
                "columns": [],
                "items": [],
                "row_count": 0,
                "affected_rows": affected,
                "message": f"执行完成，影响行数：{affected if affected >= 0 else '未知'}",
            }
        except Exception:
            connection.rollback()
            raise


def apply_table_editor_changes(table: str, changes: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not changes:
        return {"updated_rows": 0, "updated_cells": 0, "message": "没有需要写入的更改"}

    schema = get_table_editor_schema()
    table_map = {item["name"]: item for item in schema["tables"]}
    table_info = table_map.get(table)
    if table_info is None:
        raise ValueError("不支持编辑该表")

    columns = table_info["columns"]
    column_names = {column["name"] for column in columns}
    primary_columns = [column["name"] for column in columns if column.get("primary_key")]
    if not primary_columns:
        raise ValueError("该表没有主键，不能安全写入更改")

    updated_rows = 0
    updated_cells = 0
    with get_connection() as connection:
        try:
            for change in changes:
                pk_values = change.get("pk") or {}
                values = change.get("values") or {}
                if not values:
                    continue
                if any(column not in pk_values for column in primary_columns):
                    raise ValueError("更改缺少主键，不能写入")

                update_columns = [
                    column
                    for column in values
                    if column in column_names and column not in primary_columns
                ]
                if not update_columns:
                    continue

                set_sql = ", ".join(f'"{column}" = ?' for column in update_columns)
                where_sql = " AND ".join(f'"{column}" = ?' for column in primary_columns)
                params = [
                    _coerce_table_editor_value(values[column])
                    for column in update_columns
                ]
                params.extend(pk_values[column] for column in primary_columns)
                cursor = connection.execute(
                    f'UPDATE "{table}" SET {set_sql} WHERE {where_sql}',
                    params,
                )
                if cursor.rowcount:
                    updated_rows += cursor.rowcount
                    updated_cells += len(update_columns)

            if table == "recipes":
                rebuild_recipe_search_index(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        "updated_rows": updated_rows,
        "updated_cells": updated_cells,
        "message": f"已写入 {updated_cells} 个单元格，影响 {updated_rows} 行",
    }


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
            i.normalized_name AS name,
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
                    OR EXISTS (
                        SELECT 1
                        FROM ingredient_aliases AS filter_alias
                        WHERE filter_alias.ingredient_id = filter_i.id
                          AND filter_alias.alias_name = ?
                    )
                  )
            )
            """
        )
        params.extend([normalized_ingredient, normalized_ingredient])

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


def _get_table_editor_columns(connection, table_name: str) -> List[Dict[str, Any]]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [
        {
            "name": row["name"],
            "type": row["type"] or "",
            "notnull": bool(row["notnull"]),
            "primary_key": bool(row["pk"]),
            "default": row["dflt_value"],
        }
        for row in rows
    ]


def _build_table_editor_filters(filters: Dict[str, Any], column_names: List[str], list_match_mode: str = "exact") -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []
    allowed_columns = set(column_names)

    for column_name in column_names:
        raw_value = filters.get(column_name)
        if raw_value is None:
            continue
        if isinstance(raw_value, list):
            selected_values = [str(value) for value in raw_value]
            if not selected_values:
                clauses.append("1 = 0")
                continue
            if list_match_mode == "contains":
                value_clauses = []
                for value in selected_values:
                    value_clauses.append(f'COALESCE(CAST("{column_name}" AS TEXT), \'\') LIKE ?')
                    params.append(f"%{value}%")
                clauses.append("(" + " OR ".join(value_clauses) + ")")
            else:
                placeholders = ", ".join("?" for _ in selected_values)
                clauses.append(f'COALESCE(CAST("{column_name}" AS TEXT), \'\') IN ({placeholders})')
                params.extend(selected_values)
            continue
        filter_value = str(raw_value).strip()
        if not filter_value:
            continue
        if column_name not in allowed_columns:
            continue
        if filter_value.upper() == "NULL":
            clauses.append(f'"{column_name}" IS NULL')
            continue
        clauses.append(f'CAST("{column_name}" AS TEXT) LIKE ?')
        params.append(f"%{filter_value}%")

    if not clauses:
        return "", []
    return "WHERE " + " AND ".join(clauses), params


def _build_table_editor_order(columns: List[Dict[str, Any]]) -> str:
    primary_columns = [column["name"] for column in columns if column.get("primary_key")]
    if primary_columns:
        order_columns = primary_columns
    elif any(column["name"] == "id" for column in columns):
        order_columns = ["id"]
    else:
        return ""
    return "ORDER BY " + ", ".join(f'"{column}"' for column in order_columns)


def _serialize_table_editor_row(row, column_names: List[str]) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    for column_name in column_names:
        value = row[column_name]
        if isinstance(value, bytes):
            item[column_name] = f"<BLOB {len(value)} bytes>"
        else:
            item[column_name] = value
    return item


def _serialize_sql_result_row(row, column_names: List[str]) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    for index, column_name in enumerate(column_names):
        value = row[index]
        if isinstance(value, bytes):
            item[column_name] = f"<BLOB {len(value)} bytes>"
        else:
            item[column_name] = value
    return item


def _coerce_table_editor_value(value: Any) -> Any:
    if isinstance(value, str) and value.upper() == "NULL":
        return None
    return value


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
