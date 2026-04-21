from typing import Any, Dict, List

from app.db.database import get_connection


CHART_DIMENSIONS = {
    "library_section": {
        "label": "专题库分布",
        "sql": "COALESCE(NULLIF(TRIM(r.library_section), ''), '未归类')",
    },
    "section_name": {
        "label": "分组分布",
        "sql": "COALESCE(NULLIF(TRIM(r.section_name), ''), '未分组')",
    },
    "cuisine": {
        "label": "菜系分布",
        "sql": "COALESCE(NULLIF(TRIM(r.cuisine), ''), '未标注')",
    },
    "sub_cuisine": {
        "label": "亚菜系分布",
        "sql": "COALESCE(NULLIF(TRIM(r.sub_cuisine), ''), '未标注')",
    },
    "status": {
        "label": "记录类型分布",
        "sql": "CASE WHEN r.record_kind = 'backlog' THEN COALESCE(NULLIF(TRIM(r.backlog_status), ''), '待办项') ELSE '正式菜谱' END",
    },
    "tag": {
        "label": "自动标签分布",
        "sql": "COALESCE(NULLIF(TRIM(mt.name), ''), '未标注')",
        "joins": "LEFT JOIN recipe_managed_tags AS rmt ON rmt.recipe_id = r.id LEFT JOIN managed_tags AS mt ON mt.id = rmt.managed_tag_id",
    },
    "ingredient": {
        "label": "食材分布",
        "sql": "COALESCE(NULLIF(TRIM(COALESCE(i.normalized_name, i.name)), ''), '未标注')",
        "joins": "LEFT JOIN recipe_ingredients AS ri ON ri.recipe_id = r.id LEFT JOIN ingredients AS i ON i.id = ri.ingredient_id",
    },
}

SCOPE_OPTIONS = {
    "all": {"label": "全部记录", "where": []},
    "recipe": {"label": "正式菜谱", "where": ["r.record_kind = 'recipe'"]},
    "backlog": {"label": "待办项", "where": ["r.record_kind = 'backlog'"]},
    "bmd": {"label": "仅 BMD", "where": ["r.bmd_flag = 1"]},
    "cc": {"label": "仅 CC", "where": ["r.cc_flag = 1"]},
    "with_method": {"label": "有做法", "where": ["r.steps_text IS NOT NULL", "TRIM(r.steps_text) <> ''"]},
    "without_method": {"label": "缺少做法", "where": ["r.steps_text IS NULL OR TRIM(r.steps_text) = ''"]},
}


def get_analytics_summary(dimension: str = "library_section", scope: str = "all", top_n: int = 12) -> Dict[str, Any]:
    safe_dimension = dimension if dimension in CHART_DIMENSIONS else "library_section"
    safe_scope = scope if scope in SCOPE_OPTIONS else "all"
    safe_top_n = max(5, min(top_n, 30))

    with get_connection() as connection:
        summary_row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN record_kind = 'recipe' THEN 1 ELSE 0 END) AS recipe_count,
                SUM(CASE WHEN record_kind = 'backlog' THEN 1 ELSE 0 END) AS backlog_count,
                COUNT(DISTINCT library_section) AS library_section_count,
                SUM(CASE WHEN steps_text IS NOT NULL AND TRIM(steps_text) <> '' THEN 1 ELSE 0 END) AS record_with_method_count,
                (SELECT COUNT(*) FROM ingredients) AS ingredient_count,
                (SELECT COUNT(*) FROM import_batches) AS import_batch_count
            FROM recipes
            """
        ).fetchone()

        chart_rows = _load_chart_rows(connection, safe_dimension, safe_scope, safe_top_n)

    return {
        "summary": {
            "recipe_count": summary_row["recipe_count"] or 0,
            "backlog_count": summary_row["backlog_count"] or 0,
            "library_section_count": summary_row["library_section_count"] or 0,
            "record_with_method_count": summary_row["record_with_method_count"] or 0,
            "ingredient_count": summary_row["ingredient_count"] or 0,
            "import_batch_count": summary_row["import_batch_count"] or 0,
        },
        "chart": {
            "dimension": safe_dimension,
            "dimension_label": CHART_DIMENSIONS[safe_dimension]["label"],
            "scope": safe_scope,
            "scope_label": SCOPE_OPTIONS[safe_scope]["label"],
            "top_n": safe_top_n,
            "items": _serialize_rows(chart_rows),
        },
        "options": {
            "dimensions": [{"value": key, "label": value["label"]} for key, value in CHART_DIMENSIONS.items()],
            "scopes": [{"value": key, "label": value["label"]} for key, value in SCOPE_OPTIONS.items()],
        },
    }


def _load_chart_rows(connection, dimension: str, scope: str, top_n: int):
    config = CHART_DIMENSIONS[dimension]
    joins = config.get("joins", "")
    where_clauses = list(SCOPE_OPTIONS[scope]["where"])

    if dimension == "tag":
        where_clauses.append("mt.name IS NOT NULL")
    if dimension == "ingredient":
        where_clauses.append("COALESCE(i.normalized_name, i.name) IS NOT NULL")

    where_sql = f"WHERE {' AND '.join(f'({item})' for item in where_clauses)}" if where_clauses else ""
    group_by_expression = "label" if dimension in {"tag", "ingredient"} else config["sql"]

    query = f"""
        SELECT
            {config['sql']} AS label,
            COUNT(DISTINCT r.id) AS value
        FROM recipes AS r
        {joins}
        {where_sql}
        GROUP BY {group_by_expression}
        ORDER BY value DESC, label
        LIMIT ?
    """
    return connection.execute(query, (top_n,)).fetchall()


def _serialize_rows(rows) -> List[Dict[str, Any]]:
    return [{"label": row["label"], "value": row["value"]} for row in rows]
