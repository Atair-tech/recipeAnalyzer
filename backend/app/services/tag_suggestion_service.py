from typing import Any, Dict, List, Optional

from app.db.database import get_connection


PLANT_INGREDIENT_KEYWORDS = {
    "豆腐",
    "番茄",
    "土豆",
    "青椒",
    "茄子",
    "黄瓜",
    "白菜",
    "生菜",
    "西兰花",
    "香菇",
    "蘑菇",
    "木耳",
    "南瓜",
    "冬瓜",
    "丝瓜",
}

MEAT_INGREDIENT_KEYWORDS = {
    "鸡",
    "鸭",
    "鱼",
    "虾",
    "牛",
    "猪",
    "羊",
    "排骨",
    "培根",
    "火腿",
    "香肠",
}


def suggest_tags_for_recipe(recipe_id: int, limit: int = 8) -> Optional[Dict[str, Any]]:
    with get_connection() as connection:
        recipe = _load_recipe_snapshot(connection, recipe_id)
        if recipe is None:
            return None

        existing_tags = set(recipe["tags"])
        suggestions: Dict[str, Dict[str, Any]] = {}

        for suggestion in _rule_based_suggestions(recipe):
            if suggestion["tag"] in existing_tags:
                continue
            _merge_suggestion(suggestions, suggestion)

        for suggestion in _similar_recipe_suggestions(connection, recipe):
            if suggestion["tag"] in existing_tags:
                continue
            _merge_suggestion(suggestions, suggestion)

    ranked = sorted(
        suggestions.values(),
        key=lambda item: (-item["confidence"], item["tag"]),
    )

    return {
        "recipe_id": recipe_id,
        "recipe_name": recipe["name"],
        "existing_tags": recipe["tags"],
        "items": ranked[: max(1, min(limit, 15))],
    }


def _load_recipe_snapshot(connection, recipe_id: int) -> Optional[Dict[str, Any]]:
    recipe_row = connection.execute(
        """
        SELECT
            id,
            name,
            record_kind,
            backlog_status,
            library_section,
            section_name,
            cuisine,
            ingredients_text,
            seasonings_text,
            steps_text,
            notes_text
        FROM recipes
        WHERE id = ?
        """,
        (recipe_id,),
    ).fetchone()

    if recipe_row is None:
        return None

    tag_rows = connection.execute(
        """
        SELECT t.name
        FROM recipe_tags AS rt
        INNER JOIN tags AS t ON t.id = rt.tag_id
        WHERE rt.recipe_id = ?
        ORDER BY t.name
        """,
        (recipe_id,),
    ).fetchall()
    ingredient_rows = connection.execute(
        """
        SELECT COALESCE(i.normalized_name, i.name) AS ingredient_name
        FROM recipe_ingredients AS ri
        INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
        WHERE ri.recipe_id = ?
        ORDER BY ri.id
        """,
        (recipe_id,),
    ).fetchall()

    return {
        "id": recipe_row["id"],
        "name": recipe_row["name"],
        "record_kind": recipe_row["record_kind"] or "",
        "backlog_status": recipe_row["backlog_status"] or "",
        "library_section": recipe_row["library_section"] or "",
        "section_name": recipe_row["section_name"] or "",
        "cuisine": recipe_row["cuisine"] or "",
        "ingredients_text": recipe_row["ingredients_text"] or "",
        "seasonings_text": recipe_row["seasonings_text"] or "",
        "steps_text": recipe_row["steps_text"] or "",
        "notes_text": recipe_row["notes_text"] or "",
        "tags": [row["name"] for row in tag_rows],
        "ingredients": [row["ingredient_name"] for row in ingredient_rows],
    }


def _rule_based_suggestions(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    combined_text = " ".join(
        [
            recipe["library_section"],
            recipe["section_name"],
            recipe["cuisine"],
            recipe["ingredients_text"],
            recipe["seasonings_text"],
            recipe["steps_text"],
            recipe["notes_text"],
        ]
    )

    if recipe["record_kind"] == "backlog":
        suggestions.append(_suggestion(recipe["backlog_status"] or "待办事项", 0.96, "rule", "来自待办工作表状态字段"))
        return suggestions

    if recipe["library_section"]:
        suggestions.append(_suggestion(recipe["library_section"], 0.9, "rule", f"专题库为 {recipe['library_section']}"))

    if recipe["section_name"]:
        suggestions.append(_suggestion(recipe["section_name"], 0.82, "rule", f"分组为 {recipe['section_name']}"))

    if recipe["cuisine"]:
        suggestions.append(_suggestion(recipe["cuisine"], 0.88, "rule", f"菜系字段为 {recipe['cuisine']}"))

    if _is_vegetable_focused(recipe["ingredients"]):
        suggestions.append(_suggestion("素菜倾向", 0.68, "rule", "结构化食材以蔬菜和豆制品为主"))

    if any(keyword in combined_text for keyword in ("煲仔饭", "盖饭", "炒饭", "拌饭")):
        suggestions.append(_suggestion("米饭类", 0.66, "rule", "名称或做法包含米饭类关键词"))

    if any(keyword in combined_text for keyword in ("面", "粉", "意面", "米线")):
        suggestions.append(_suggestion("面粉类", 0.63, "rule", "名称或做法包含面条/粉类关键词"))

    if any(keyword in combined_text for keyword in ("凉拌", "冷盘", "沙拉")):
        suggestions.append(_suggestion("凉菜", 0.7, "rule", "做法特征偏冷菜或拌菜"))

    return suggestions


def _similar_recipe_suggestions(connection, recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidate_rows = connection.execute(
        """
        SELECT
            r.id,
            r.library_section,
            r.section_name,
            r.cuisine
        FROM recipes AS r
        WHERE r.id <> ?
        """,
        (recipe["id"],),
    ).fetchall()

    recipe_ingredients = set(recipe["ingredients"])
    recipe_tags = set(recipe["tags"])

    candidate_scores: Dict[int, float] = {}
    shared_ingredient_counts: Dict[int, int] = {}
    for row in candidate_rows:
        score = 0.0
        if row["library_section"] and row["library_section"] == recipe["library_section"]:
            score += 2.2
        if row["section_name"] and row["section_name"] == recipe["section_name"]:
            score += 1.6
        if row["cuisine"] and row["cuisine"] == recipe["cuisine"]:
            score += 1.8
        if score > 0:
            candidate_scores[row["id"]] = score

    if recipe_ingredients:
        ingredient_match_rows = connection.execute(
            """
            SELECT
                ri.recipe_id,
                COUNT(*) AS shared_ingredient_count
            FROM recipe_ingredients AS ri
            INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id <> ?
              AND COALESCE(i.normalized_name, i.name) IN ({placeholders})
            GROUP BY ri.recipe_id
            """.format(placeholders=", ".join("?" for _ in recipe_ingredients)),
            [recipe["id"], *recipe_ingredients],
        ).fetchall()

        for row in ingredient_match_rows:
            shared_ingredient_counts[row["recipe_id"]] = row["shared_ingredient_count"]
            candidate_scores[row["recipe_id"]] = candidate_scores.get(row["recipe_id"], 0.0) + row["shared_ingredient_count"] * 1.6

    if not candidate_scores:
        return []

    candidate_ids = [
        recipe_id
        for recipe_id in sorted(candidate_scores, key=lambda value: candidate_scores[value], reverse=True)
        if candidate_scores[recipe_id] >= 3.8 and shared_ingredient_counts.get(recipe_id, 0) >= 1
    ][:8]

    if not candidate_ids:
        return []

    tag_rows = connection.execute(
        """
        SELECT
            rt.recipe_id,
            t.name
        FROM recipe_tags AS rt
        INNER JOIN tags AS t ON t.id = rt.tag_id
        WHERE rt.recipe_id IN ({placeholders})
        """.format(placeholders=", ".join("?" for _ in candidate_ids)),
        candidate_ids,
    ).fetchall()

    aggregated: Dict[str, Dict[str, Any]] = {}
    support_counts: Dict[str, int] = {}
    for row in tag_rows:
        tag_name = row["name"]
        if tag_name in recipe_tags:
            continue

        similarity_score = candidate_scores.get(row["recipe_id"], 0.0)
        entry = aggregated.setdefault(
            tag_name,
            {
                "tag": tag_name,
                "confidence": 0.0,
                "source": "similar_recipes",
                "reason": "与相似菜谱标签共现",
            },
        )
        entry["confidence"] += similarity_score / 10
        support_counts[tag_name] = support_counts.get(tag_name, 0) + 1

    suggestions = []
    for entry in aggregated.values():
        entry["confidence"] = min(0.86, round(entry["confidence"], 2))
        if entry["confidence"] >= 0.3 and support_counts.get(entry["tag"], 0) >= 2:
            suggestions.append(entry)
    return suggestions


def _is_vegetable_focused(ingredients: List[str]) -> bool:
    if not ingredients:
        return False

    meat_hits = sum(any(keyword in ingredient for keyword in MEAT_INGREDIENT_KEYWORDS) for ingredient in ingredients)
    plant_hits = sum(any(keyword in ingredient for keyword in PLANT_INGREDIENT_KEYWORDS) for ingredient in ingredients)
    return plant_hits >= 1 and meat_hits == 0


def _suggestion(tag: str, confidence: float, source: str, reason: str) -> Dict[str, Any]:
    return {
        "tag": tag,
        "confidence": confidence,
        "source": source,
        "reason": reason,
    }


def _merge_suggestion(bucket: Dict[str, Dict[str, Any]], suggestion: Dict[str, Any]) -> None:
    existing = bucket.get(suggestion["tag"])
    if existing is None:
        bucket[suggestion["tag"]] = dict(suggestion)
        return

    if suggestion["confidence"] > existing["confidence"]:
        existing["confidence"] = suggestion["confidence"]
    existing["reason"] = f"{existing['reason']}；{suggestion['reason']}"
    existing["source"] = f"{existing['source']}+{suggestion['source']}"
