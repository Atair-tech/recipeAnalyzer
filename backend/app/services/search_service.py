import re
import sqlite3
from typing import Any, Dict, List, Optional, Set

from app.db.database import get_connection


NEGATION_PATTERNS = ("不要", "不放", "不含", "别放")


def rebuild_recipe_search_index(connection=None) -> None:
    owns_connection = connection is None
    if owns_connection:
        manager = get_connection()
        connection = manager.__enter__()

    try:
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS recipe_search
                USING fts5(
                    recipe_id UNINDEXED,
                    search_text,
                    tokenize = 'unicode61 remove_diacritics 0'
                )
                """
            )
            connection.execute("DELETE FROM recipe_search")
        except sqlite3.OperationalError:
            if owns_connection:
                connection.rollback()
            return

        rows = connection.execute(
            """
            SELECT
                r.id,
                r.name,
                r.record_kind,
                r.backlog_status,
                r.library_section,
                r.section_name,
                r.category,
                r.cuisine,
                r.sub_cuisine,
                r.source_reference,
                r.ingredients_text,
                r.seasonings_text,
                r.steps_text,
                r.notes_text,
                GROUP_CONCAT(DISTINCT t.name) AS tag_names
            FROM recipes AS r
            LEFT JOIN recipe_tags AS rt ON rt.recipe_id = r.id
            LEFT JOIN tags AS t ON t.id = rt.tag_id
            GROUP BY r.id
            """
        ).fetchall()

        for row in rows:
            search_text = " ".join(
                value
                for value in [
                    row["name"],
                    row["record_kind"],
                    row["backlog_status"],
                    row["library_section"],
                    row["section_name"],
                    row["category"],
                    row["cuisine"],
                    row["sub_cuisine"],
                    row["source_reference"],
                    row["ingredients_text"],
                    row["seasonings_text"],
                    row["steps_text"],
                    row["notes_text"],
                    row["tag_names"],
                ]
                if value
            )
            connection.execute(
                """
                INSERT INTO recipe_search (recipe_id, search_text)
                VALUES (?, ?)
                """,
                (row["id"], search_text),
            )

        if owns_connection:
            connection.commit()
    finally:
        if owns_connection:
            manager.__exit__(None, None, None)


def natural_search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    extra_terms: Optional[List[str]] = None,
    structured_understanding: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_query = (query or "").strip()
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    if not normalized_query:
        return {
            "query": "",
            "understanding": _empty_understanding(),
            "items": [],
            "total": 0,
            "limit": safe_limit,
            "offset": safe_offset,
        }

    with get_connection() as connection:
        understanding = _understand_query(connection, normalized_query)
        if structured_understanding:
            understanding = _merge_structured_understanding(understanding, structured_understanding)
        if extra_terms:
            normalized_extra_terms = _normalize_external_terms(extra_terms)
            understanding["expanded_terms"] = _dedupe_preserve_order(
                understanding.get("expanded_terms", []) + normalized_extra_terms
            )
            understanding["free_text_terms"] = _dedupe_preserve_order(
                understanding["free_text_terms"] + normalized_extra_terms
            )
        candidate_scores = _load_fts_candidates(connection, understanding["free_text_terms"], limit=240)
        candidate_ids = None if _has_structured_constraints(understanding) else candidate_scores.keys()
        recipes = _load_candidate_recipes(connection, candidate_ids if candidate_scores else None)

    ranked_items = []
    for recipe in recipes:
        ranking = _rank_recipe(recipe, understanding, candidate_scores)
        if ranking is None:
            continue
        ranked_items.append(ranking)

    ranked_items.sort(
        key=lambda item: (
            -item["score"],
            item["library_section"] or "",
            item["section_name"] or "",
            item["name"],
        )
    )

    return {
        "query": normalized_query,
        "understanding": understanding,
        "total": len(ranked_items),
        "limit": safe_limit,
        "offset": safe_offset,
        "items": ranked_items[safe_offset : safe_offset + safe_limit],
    }


def _has_structured_constraints(understanding: Dict[str, Any]) -> bool:
    return any(
        understanding.get(key)
        for key in (
            "library_sections",
            "section_names",
            "cuisines",
            "statuses",
            "include_ingredients",
            "exclude_ingredients",
        )
    )


def get_natural_search_export_rows(query: str) -> List[Dict[str, Any]]:
    result = natural_search(query=query, limit=10000, offset=0)
    rows: List[Dict[str, Any]] = []
    for item in result["items"]:
        rows.append(
            {
                "菜名": item["name"],
                "记录类型": item["backlog_status"] if item["record_kind"] == "backlog" else "正式菜谱",
                "专题库": item["library_section"] or "",
                "分组": item["section_name"] or "",
                "菜系": item["cuisine"] or "",
                "亚菜系": item["sub_cuisine"] or "",
                "标签": "、".join(item["tags"]),
                "食材": "、".join(item["ingredients"]),
                "BMD": "是" if item["bmd_flag"] else "",
                "CC": "是" if item["cc_flag"] else "",
                "得分": item["score"],
                "命中原因": "；".join(item["reasons"]),
            }
        )
    return rows


def _empty_understanding() -> Dict[str, Any]:
    return {
        "free_text_terms": [],
        "expanded_terms": [],
        "library_sections": [],
        "section_names": [],
        "cuisines": [],
        "statuses": [],
        "include_ingredients": [],
        "exclude_ingredients": [],
        "prefer_terms": [],
        "external_source": "",
    }


def _merge_structured_understanding(
    base: Dict[str, Any],
    external: Dict[str, Any],
) -> Dict[str, Any]:
    include_terms = _normalize_external_terms(external.get("include_terms"))
    exclude_terms = _normalize_external_terms(external.get("exclude_terms"))
    prefer_terms = _normalize_external_terms(external.get("prefer_terms"))
    search_terms = _normalize_external_terms(external.get("search_terms"))
    expanded_terms = _normalize_external_terms(external.get("expanded_terms"))
    constraints = _normalize_external_terms(external.get("constraints"))

    base["include_ingredients"] = _dedupe_preserve_order(base["include_ingredients"] + include_terms)
    base["exclude_ingredients"] = _dedupe_preserve_order(base["exclude_ingredients"] + exclude_terms)
    base["prefer_terms"] = _dedupe_preserve_order(base.get("prefer_terms", []) + prefer_terms)
    base["expanded_terms"] = _dedupe_preserve_order(
        base.get("expanded_terms", []) + expanded_terms + search_terms + prefer_terms
    )
    base["free_text_terms"] = _dedupe_preserve_order(
        base["free_text_terms"] + search_terms + include_terms + prefer_terms + constraints
    )
    base["external_source"] = str(external.get("source") or "").strip()
    return base


def _normalize_external_terms(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value:
        if isinstance(item, dict):
            candidates = [
                item.get("term"),
                item.get("name"),
                item.get("value"),
                item.get("text"),
                item.get("keyword"),
            ]
            text = next((str(candidate).strip() for candidate in candidates if str(candidate or "").strip()), "")
        else:
            text = str(item or "").strip()
        if text:
            normalized.append(text)
    return _dedupe_preserve_order(normalized)


def _understand_query(connection, query: str) -> Dict[str, Any]:
    known = _load_known_values(connection)
    understanding = _empty_understanding()
    remaining = query

    for status in ("待挑战", "待记录", "正式菜谱"):
        if status in remaining:
            understanding["statuses"].append(status)
            remaining = remaining.replace(status, " ")

    for section in sorted(known["library_sections"], key=len, reverse=True):
        if section and section in remaining:
            understanding["library_sections"].append(section)
            remaining = remaining.replace(section, " ")

    for group_name in sorted(known["section_names"], key=len, reverse=True):
        if group_name and group_name in remaining:
            understanding["section_names"].append(group_name)
            remaining = remaining.replace(group_name, " ")

    for cuisine in sorted(known["cuisines"], key=len, reverse=True):
        if cuisine and cuisine in remaining:
            understanding["cuisines"].append(cuisine)
            remaining = remaining.replace(cuisine, " ")

    for ingredient in sorted(known["ingredients"], key=len, reverse=True):
        if not ingredient or ingredient not in query:
            continue

        if any(f"{prefix}{ingredient}" in query for prefix in NEGATION_PATTERNS):
            understanding["exclude_ingredients"].append(ingredient)
            for prefix in NEGATION_PATTERNS:
                remaining = remaining.replace(f"{prefix}{ingredient}", " ")
            continue

        understanding["include_ingredients"].append(ingredient)
        remaining = remaining.replace(ingredient, " ")

    for match in re.finditer(r"(不要|不放|不含|别放)([\u4e00-\u9fff]{1,8})", query):
        candidate = match.group(2).strip()
        if candidate:
            understanding["exclude_ingredients"].append(candidate)
            remaining = remaining.replace(match.group(0), " ")

    if any(term in query for term in ("不辣", "不要辣", "不能辣", "别辣", "少辣")):
        understanding["exclude_ingredients"].extend(
            [
                "辣",
                "辣椒",
                "干辣椒",
                "小米辣",
                "辣酱",
                "辣油",
                "卡宴",
                "cayenne",
                "冬阴功",
                "哈里萨",
                "harissa",
            ]
        )
        remaining = re.sub(r"(不辣|不要辣|不能辣|别辣|少辣)", " ", remaining)

    understanding["free_text_terms"] = _extract_query_terms(remaining)
    for key in ("library_sections", "section_names", "cuisines", "statuses", "include_ingredients", "exclude_ingredients"):
        understanding[key] = _dedupe_preserve_order(understanding[key])
    return understanding


def _load_known_values(connection) -> Dict[str, List[str]]:
    library_section_rows = connection.execute(
        "SELECT DISTINCT library_section FROM recipes WHERE library_section IS NOT NULL AND TRIM(library_section) <> '' ORDER BY library_section"
    ).fetchall()
    section_rows = connection.execute(
        "SELECT DISTINCT section_name FROM recipes WHERE section_name IS NOT NULL AND TRIM(section_name) <> '' ORDER BY section_name"
    ).fetchall()
    cuisine_rows = connection.execute(
        "SELECT DISTINCT cuisine FROM recipes WHERE cuisine IS NOT NULL AND TRIM(cuisine) <> '' ORDER BY cuisine"
    ).fetchall()
    ingredient_rows = connection.execute(
        """
        SELECT DISTINCT normalized_name AS ingredient_name
        FROM ingredients
        WHERE normalized_name IS NOT NULL
          AND TRIM(normalized_name) <> ''
          AND is_visible = 1
          AND LENGTH(TRIM(normalized_name)) >= 2
        ORDER BY ingredient_name
        """
    ).fetchall()
    return {
        "library_sections": [row["library_section"] for row in library_section_rows],
        "section_names": [row["section_name"] for row in section_rows],
        "cuisines": [row["cuisine"] for row in cuisine_rows],
        "ingredients": [row["ingredient_name"] for row in ingredient_rows],
    }


def _extract_query_terms(text: str) -> List[str]:
    terms = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text)
    return _dedupe_preserve_order([term.strip() for term in terms if term.strip() and not term.strip().isdigit()])


def _load_fts_candidates(connection, terms: List[str], limit: int = 160) -> Dict[int, float]:
    if not terms:
        return {}

    match_query = " OR ".join(f'"{term}"' for term in terms)

    try:
        rows = connection.execute(
            """
            SELECT recipe_id, bm25(recipe_search) AS fts_score
            FROM recipe_search
            WHERE recipe_search MATCH ?
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    return {
        row["recipe_id"]: float(row["fts_score"] or 0.0)
        for row in rows
    }


def _load_candidate_recipes(connection, candidate_ids: Optional[Set[int]]) -> List[Dict[str, Any]]:
    where_clause = ""
    params: List[Any] = []

    if candidate_ids:
        placeholders = ", ".join("?" for _ in candidate_ids)
        where_clause = f"WHERE r.id IN ({placeholders})"
        params.extend(candidate_ids)

    rows = connection.execute(
        f"""
        SELECT
            r.id,
            r.name,
            r.record_kind,
            r.backlog_status,
            r.library_section,
            r.section_name,
            r.cuisine,
            r.sub_cuisine,
            r.ingredients_text,
            r.seasonings_text,
            r.steps_text,
            r.notes_text,
            r.bmd_flag,
            r.cc_flag,
            GROUP_CONCAT(DISTINCT t.name) AS tag_names
        FROM recipes AS r
        LEFT JOIN recipe_tags AS rt ON rt.recipe_id = r.id
        LEFT JOIN tags AS t ON t.id = rt.tag_id
        {where_clause}
        GROUP BY r.id
        """,
        params,
    ).fetchall()

    ingredient_rows = connection.execute(
        """
        SELECT
            ri.recipe_id,
            i.normalized_name AS ingredient_name
        FROM recipe_ingredients AS ri
        INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
        WHERE i.is_visible = 1
        """
    ).fetchall()

    ingredient_map: Dict[int, List[str]] = {}
    for row in ingredient_rows:
        ingredient_map.setdefault(row["recipe_id"], []).append(row["ingredient_name"])

    items = []
    for row in rows:
        tags = row["tag_names"].split(",") if row["tag_names"] else []
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
                "ingredients_text": row["ingredients_text"] or "",
                "seasonings_text": row["seasonings_text"] or "",
                "steps_text": row["steps_text"] or "",
                "notes_text": row["notes_text"] or "",
                "bmd_flag": bool(row["bmd_flag"]),
                "cc_flag": bool(row["cc_flag"]),
                "tags": tags,
                "ingredients": ingredient_map.get(row["id"], []),
            }
        )

    return items


def _rank_recipe(recipe: Dict[str, Any], understanding: Dict[str, Any], candidate_scores: Dict[int, float]) -> Optional[Dict[str, Any]]:
    searchable_blob = " ".join(
        [
            recipe["name"] or "",
            recipe["library_section"] or "",
            recipe["section_name"] or "",
            recipe["cuisine"] or "",
            recipe["sub_cuisine"] or "",
            recipe["ingredients_text"] or "",
            recipe["seasonings_text"] or "",
            recipe["steps_text"] or "",
            recipe["notes_text"] or "",
            " ".join(recipe["tags"]),
            " ".join(recipe["ingredients"]),
        ]
    )

    if understanding["statuses"]:
        acceptable_statuses = set(understanding["statuses"])
        recipe_status = recipe["backlog_status"] if recipe["record_kind"] == "backlog" else "正式菜谱"
        if recipe_status not in acceptable_statuses:
            return None

    for ingredient in understanding["include_ingredients"]:
        if ingredient not in searchable_blob:
            return None

    for ingredient in understanding["exclude_ingredients"]:
        if ingredient in searchable_blob:
            return None

    score = 0.0
    reasons: List[str] = []

    if understanding["library_sections"]:
        if recipe["library_section"] in understanding["library_sections"]:
            score += 6
            reasons.append(f"专题库匹配：{recipe['library_section']}")
        else:
            return None

    if understanding["section_names"]:
        if recipe["section_name"] in understanding["section_names"]:
            score += 5
            reasons.append(f"分组匹配：{recipe['section_name']}")
        else:
            return None

    if understanding["cuisines"]:
        if recipe["cuisine"] in understanding["cuisines"] or recipe["sub_cuisine"] in understanding["cuisines"]:
            score += 5
            reasons.append(f"菜系匹配：{recipe['cuisine'] or recipe['sub_cuisine']}")
        else:
            return None

    ingredient_matches = [ingredient for ingredient in understanding["include_ingredients"] if ingredient in searchable_blob]
    if ingredient_matches:
        score += 4 * len(ingredient_matches)
        reasons.append(f"食材匹配：{'、'.join(_dedupe_preserve_order(ingredient_matches))}")

    token_hits = []
    expanded_term_set = set(understanding.get("expanded_terms", []))
    for term in understanding["free_text_terms"]:
        weight_multiplier = 0.6 if term in expanded_term_set else 1.0
        term_score = 0.0
        if term in (recipe["name"] or ""):
            term_score += 8 * weight_multiplier
        if term in (recipe["library_section"] or "") or term in (recipe["section_name"] or ""):
            term_score += 5 * weight_multiplier
        if term in (recipe["cuisine"] or "") or term in (recipe["sub_cuisine"] or ""):
            term_score += 4 * weight_multiplier
        if term in (recipe["ingredients_text"] or "") or term in (recipe["seasonings_text"] or ""):
            term_score += 3.5 * weight_multiplier
        if term in (recipe["steps_text"] or "") or term in (recipe["notes_text"] or ""):
            term_score += 2.5 * weight_multiplier
        if term in " ".join(recipe["tags"]):
            term_score += 2 * weight_multiplier
        if term_score > 0:
            token_hits.append(term)
            score += term_score

    if token_hits:
        reasons.append(f"文本命中：{'、'.join(_dedupe_preserve_order(token_hits))}")

    prefer_hits = []
    for term in understanding.get("prefer_terms", []):
        term_score = 0.0
        if term in (recipe["name"] or ""):
            term_score += 4
        if term in (recipe["library_section"] or "") or term in (recipe["section_name"] or ""):
            term_score += 3
        if term in (recipe["cuisine"] or "") or term in (recipe["sub_cuisine"] or ""):
            term_score += 2.5
        if term in (recipe["ingredients_text"] or "") or term in (recipe["seasonings_text"] or ""):
            term_score += 2
        if term in (recipe["steps_text"] or "") or term in (recipe["notes_text"] or ""):
            term_score += 1.5
        if term in " ".join(recipe["tags"]):
            term_score += 2
        if term_score > 0:
            prefer_hits.append(term)
            score += term_score

    if prefer_hits:
        reasons.append(f"偏好命中：{'、'.join(_dedupe_preserve_order(prefer_hits))}")

    if recipe["bmd_flag"]:
        score += 0.8
    if recipe["cc_flag"]:
        score += 0.8

    if recipe["id"] in candidate_scores:
        fts_bonus = max(0.5, 6 - min(5.5, abs(candidate_scores[recipe["id"]])))
        score += fts_bonus
        reasons.append("全文检索命中")

    if score <= 0:
        return None

    return {
        "id": recipe["id"],
        "name": recipe["name"],
        "record_kind": recipe["record_kind"],
        "backlog_status": recipe["backlog_status"],
        "library_section": recipe["library_section"],
        "section_name": recipe["section_name"],
        "cuisine": recipe["cuisine"],
        "sub_cuisine": recipe["sub_cuisine"],
        "tags": recipe["tags"],
        "ingredients": recipe["ingredients"],
        "bmd_flag": recipe["bmd_flag"],
        "cc_flag": recipe["cc_flag"],
        "score": round(score, 2),
        "reasons": reasons,
    }


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            cleaned.append(value)
    return cleaned
