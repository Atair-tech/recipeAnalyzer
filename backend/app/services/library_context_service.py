from typing import Any, Dict, List, Optional

from app.db.database import get_connection


MAX_ORIGINAL_TAGS = 80
MAX_INGREDIENTS = 120
MAX_CUISINES = 100
MAX_TERM_CHARS = 24


def get_library_vocabulary_summary() -> Dict[str, Any]:
    with get_connection() as connection:
        library_sections = _single_column_values(
            connection,
            """
            SELECT DISTINCT library_section AS value
            FROM recipes
            WHERE library_section IS NOT NULL AND TRIM(library_section) <> ''
            ORDER BY library_section
            """,
        )
        section_names = _single_column_values(
            connection,
            """
            SELECT DISTINCT section_name AS value
            FROM recipes
            WHERE section_name IS NOT NULL AND TRIM(section_name) <> ''
            ORDER BY section_name
            """,
        )
        cuisines = _filter_cuisine_terms(_single_column_values(
            connection,
            """
            SELECT DISTINCT cuisine AS value
            FROM recipes
            WHERE cuisine IS NOT NULL AND TRIM(cuisine) <> ''
            UNION
            SELECT DISTINCT sub_cuisine AS value
            FROM recipes
            WHERE sub_cuisine IS NOT NULL AND TRIM(sub_cuisine) <> ''
            ORDER BY value
            """,
        ))[:MAX_CUISINES]
        original_tags = _single_column_values(
            connection,
            """
            SELECT t.name AS value, COUNT(rt.recipe_id) AS usage_count
            FROM tags AS t
            LEFT JOIN recipe_tags AS rt ON rt.tag_id = t.id
            GROUP BY t.id
            ORDER BY usage_count DESC, t.name
            LIMIT ?
            """,
            [MAX_ORIGINAL_TAGS],
        )
        managed_tags = [
            {
                "name": row["name"],
                "description": _clip(row["description"] or "", 60),
            }
            for row in connection.execute(
                """
                SELECT name, description
                FROM managed_tags
                WHERE is_active = 1
                ORDER BY sort_order ASC, name ASC
                """
            ).fetchall()
            if row["name"]
        ]
        visible_ingredients = _single_column_values(
            connection,
            """
            SELECT i.normalized_name AS value, COUNT(ri.recipe_id) AS usage_count
            FROM ingredients AS i
            LEFT JOIN recipe_ingredients AS ri ON ri.ingredient_id = i.id
            WHERE i.is_visible = 1
              AND i.normalized_name IS NOT NULL
              AND TRIM(i.normalized_name) <> ''
            GROUP BY value
            ORDER BY usage_count DESC, value ASC
            LIMIT ?
            """,
            [MAX_INGREDIENTS],
        )

    return {
        "library_sections": library_sections,
        "section_names": section_names,
        "cuisines": cuisines,
        "original_tags": original_tags,
        "managed_tags": managed_tags,
        "visible_ingredients": visible_ingredients,
    }


def format_library_vocabulary_summary(summary: Dict[str, Any]) -> str:
    managed_tag_lines = [
        f"{item['name']}（{item['description']}）" if item.get("description") else str(item.get("name") or "")
        for item in summary.get("managed_tags", [])
        if item.get("name")
    ]
    lines = [
        "库内低风险词表摘要（仅用于构建查询，不包含具体菜谱正文）：",
        f"- 专题库: {_join(summary.get('library_sections', []))}",
        f"- 分组: {_join(summary.get('section_names', []))}",
        f"- 菜系/亚菜系: {_join(summary.get('cuisines', []))}",
        f"- 自动标签: {_join(managed_tag_lines)}",
        f"- 原始标签: {_join(summary.get('original_tags', []))}",
        f"- 高频可见食材: {_join(summary.get('visible_ingredients', []))}",
    ]
    return "\n".join(lines)


def _single_column_values(
    connection,
    sql: str,
    params: Optional[List[Any]] = None,
    max_items: Optional[int] = None,
) -> List[str]:
    rows = connection.execute(sql, params or []).fetchall()
    result: List[str] = []
    seen = set()
    for row in rows:
        value = _normalize_term(row["value"])
        if not value or _looks_noisy_term(value):
            continue
        if value and value not in seen:
            result.append(value)
            seen.add(value)
        if max_items and len(result) >= max_items:
            break
    return result


def _join(values: List[str]) -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "、".join(cleaned) if cleaned else "-"


def _normalize_term(value: Any) -> str:
    return " ".join(str(value or "").replace("\u3000", " ").split()).strip()


def _looks_noisy_term(value: str) -> bool:
    if len(value) > MAX_TERM_CHARS:
        return True
    if any(char.isdigit() for char in value):
        return True
    noisy_markers = ("下次", "虽然", "但是", "可用于", "版本", "http", "www", "（", "）", "(", ")")
    return any(marker in value for marker in noisy_markers)


def _filter_cuisine_terms(values: List[str]) -> List[str]:
    cuisine_markers = (
        "菜",
        "料理",
        "地域",
        "口味",
        "欧美",
        "地中海",
        "东南亚",
        "中东",
        "亚洲",
        "阿拉伯",
        "广东/贵州",
        "其他",
    )
    result: List[str] = []
    for value in values:
        if any("A" <= char <= "z" for char in value):
            continue
        if any(marker in value for marker in cuisine_markers):
            result.append(value)
    return result


def _clip(value: str, max_chars: int) -> str:
    text = _normalize_term(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip(" ，,。、；;") + "..."
