import hashlib
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional

from app.db.database import get_connection
from app.services.ai_log_service import create_ai_conversation_log
from app.services.ingredient_service import parse_ingredients_text, normalize_ingredient_name, sync_recipe_ingredients_from_items
from app.services.ollama_service import OLLAMA_DEFAULT_MODEL, _call_ollama_chat as _ollama_chat_impl
from app.services.refine_hash_service import build_refinement_source_hash


REFINE_PROMPT_VERSION = "import-refine-v6-no-think-compact"
COMPATIBLE_REFINE_VERSIONS = {
    "1f7dcba16db8b4a59ad9ff00dd3da139753ec5bdf0f62306675818f3ad9e1459",
    "ff0f5ea05854a0ac7b400030449eb3a5247fe1c8dc45411200c6286333d46a6e",
}

INGREDIENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "amount": {"type": "string"},
                    "unit": {"type": "string"},
                    "remark": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ingredients"],
    "additionalProperties": False,
}

OPTIONAL_PREFIXES = ("可加", "可放", "可用", "也可用", "也可加", "建议加", "最后加")
OPTIONAL_SUFFIXES = ("可加", "可放", "可用", "也可用", "更好吃", "提味", "增香")
DROP_HINTS = (
    "%",
    "/",
    "\\",
    "*",
    "+",
    "=",
    "正常来说",
    "经典",
    "低卡",
    "口味",
    "含水量",
    "左右",
    "以上",
    "建议",
    "推荐",
    "如果",
    "或者",
    "然后",
    "需要",
    "常用食材",
    "原版",
)
BRAND_PREFIXES = (
    "六必居",
    "暴肌独角兽",
    "薄荷记",
    "顶丰",
    "李锦记",
    "盒马",
    "牛头牌",
    "都乐",
    "和润",
    "欧萨",
    "单山",
    "广合",
    "圃美多",
)
GENERIC_PREFIXES = ("点缀用的", "搭配用的", "佐餐用的", "原版用的", "可选搭配", "搭配蔬菜")
INGREDIENT_SEGMENTS = (
    "小葱花",
    "葡萄叶",
    "鸡胸肉",
    "鸡腿肉",
    "整鸡",
    "鸡腿",
    "鸡翅",
    "鸡块",
    "薄荷",
    "欧芹",
    "莳萝",
    "海带",
    "裙带菜",
    "花蛤",
    "蛤蜊",
    "料酒",
    "南瓜",
    "土豆",
    "红薯",
    "茄子",
    "豆角",
    "彩椒",
    "尖椒",
    "麻椒",
    "雪菜",
    "青菜",
    "姜片",
    "糖",
)
SECTION_LABELS = (
    "蛤蜊水",
    "汤底",
    "淋面",
    "腌料",
    "酱汁",
    "料汁",
    "汤汁",
    "主料",
    "辅料",
    "配料",
    "配菜",
    "调料",
    "调味",
    "香料",
    "卤料",
)
AMOUNT_IN_NAME_PATTERN = re.compile(r"(?P<prefix>.*?)(?P<amount>\d+(?:\.\d+)?)(?P<unit>g|kg|ml|mL|L|l|克|千克|毫升|公升)$", re.I)
REFINE_EXTRA_UNITS = {"tsp", "tbsp", "teaspoon", "tablespoon"}
PACKAGE_HINT_PATTERN = re.compile(r"(半包|半袋|一包|一袋|半盒|一盒)$")
FALLBACK_SPLIT_PATTERN = re.compile(r"[，,、；;]")
FALLBACK_CHOICE_PATTERN = re.compile(r"(?:/|／|\\|or|OR|或)")
SECTION_HEADING_PATTERN = re.compile(r"[【\[][^】\]]+[】\]]")

_job_lock = threading.Lock()
_job_state = {
    "run_id": None,
    "thread": None,
    "pause_requested": False,
}


class RefineGenerationError(RuntimeError):
    def __init__(self, message: str, *, raw_response: Optional[str] = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


def _call_ollama_chat(
    model_name: str,
    messages: List[Dict[str, str]],
    *,
    response_format: Optional[Any] = None,
    max_attempts: int = 1,
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _ollama_chat_impl(
                model_name,
                messages,
                response_format=response_format,
                extra_options={"temperature": 0.1, "num_ctx": 2048, "num_predict": 1536},
            )
        except Exception as error:
            last_error = error
            if "timed out" not in str(error).lower() or attempt >= max_attempts:
                raise
            time.sleep(0.5)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Ollama call failed without an error")


def get_refine_status() -> Dict[str, Any]:
    with get_connection() as connection:
        run = _load_latest_run(connection)

    with _job_lock:
        is_running = bool(_job_state["thread"] and _job_state["thread"].is_alive())
        pause_requested = bool(_job_state["pause_requested"])

    return {
        "run": run,
        "is_running": is_running,
        "pause_requested": pause_requested,
    }


def start_refine_run(model: Optional[str] = None) -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("A refine run is already in progress")

    model_name = (model or OLLAMA_DEFAULT_MODEL).strip()

    with get_connection() as connection:
        total_count = connection.execute(
            "SELECT COUNT(*) FROM recipes WHERE record_kind = 'recipe'"
        ).fetchone()[0]
        refine_version = _build_refine_version()
        cursor = connection.execute(
            """
            INSERT INTO ai_refine_runs (
                model,
                status,
                total_count,
                refine_version,
                started_at,
                updated_at
            )
            VALUES (?, 'running', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (model_name, total_count, refine_version),
        )
        run_id = cursor.lastrowid
        connection.commit()

    thread = threading.Thread(
        target=_run_refine_job,
        args=(run_id, model_name, refine_version),
        daemon=True,
        name=f"recipe-refine-{run_id}",
    )
    with _job_lock:
        _job_state["run_id"] = run_id
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_refine_status()


def pause_refine_run() -> Dict[str, Any]:
    with _job_lock:
        if not (_job_state["thread"] and _job_state["thread"].is_alive()):
            return get_refine_status()
        _job_state["pause_requested"] = True
    return get_refine_status()


def resume_refine_run() -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("A refine run is already in progress")

    with get_connection() as connection:
        run = connection.execute(
            """
            SELECT id, model, refine_version, status
            FROM ai_refine_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if run is None or run["status"] != "paused":
        raise ValueError("No paused refine run available")

    thread = threading.Thread(
        target=_run_refine_job,
        args=(run["id"], run["model"], run["refine_version"]),
        daemon=True,
        name=f"recipe-refine-{run['id']}",
    )
    with _job_lock:
        _job_state["run_id"] = run["id"]
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_refine_status()


def _should_skip_recipe_refinement(
    recipe_id: int,
    source_hash: str,
    model_name: str,
    refine_version: str,
    legacy_source_hash: Optional[str] = None,
) -> bool:
    with get_connection() as connection:
        state_row = connection.execute(
            """
            SELECT source_hash, model, refine_version, last_error
            FROM recipe_ai_refine_state
            WHERE recipe_id = ?
            """,
            (recipe_id,),
        ).fetchone()

    return bool(
        state_row is not None
        and (state_row["source_hash"] or "") in {source_hash or "", legacy_source_hash or ""}
        and state_row["model"] == model_name
        and _is_compatible_refine_version(state_row["refine_version"], refine_version)
        and not (state_row["last_error"] or "").strip()
        and not _has_suspicious_refined_ingredients(recipe_id)
    )


def _is_compatible_refine_version(stored_version: Optional[str], current_version: str) -> bool:
    if stored_version == current_version:
        return True
    return bool(stored_version and stored_version in COMPATIBLE_REFINE_VERSIONS)


def _has_suspicious_refined_ingredients(recipe_id: int) -> bool:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT i.normalized_name AS name, ri.amount, ri.unit
            FROM recipe_ingredients AS ri
            INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            """,
            (recipe_id,),
        ).fetchall()

    for row in rows:
        name = str(row["name"] or "").strip()
        amount = str(row["amount"] or "").strip()
        unit = str(row["unit"] or "").strip()
        if _should_drop_refined_name(name):
            return True
        if re.search(r"[A-Za-z]", name):
            return True
        if re.fullmatch(r"\d+(?:\.\d+)?(?:g|kg|ml|l|L|mL)?", name, flags=re.I):
            return True
        if "ingredient" in name.lower() or "词条" in name or "見" in name or "见" in name:
            return True
        repaired_name, _, _, _ = _repair_quantity_in_name(name, amount or None, unit or None, None)
        if repaired_name != name:
            return True
        if amount and unit and amount.lower().endswith(unit.lower()):
            return True
    return False


def _run_refine_job(run_id: int, model_name: str, refine_version: str) -> None:
    try:
        with get_connection() as connection:
            recipes = connection.execute(
                """
                SELECT
                    id,
                    name,
                    source_hash,
                    library_section,
                    section_name,
                    ingredients_text,
                    seasonings_text
                FROM recipes
                WHERE record_kind = 'recipe'
                ORDER BY id
                """
            ).fetchall()

        pending_recipes = []
        skipped_count = 0
        for recipe_row in recipes:
            recipe_id = int(recipe_row["id"])
            source_hash = build_refinement_source_hash(dict(recipe_row))
            legacy_source_hash = recipe_row["source_hash"] or ""
            if _should_skip_recipe_refinement(recipe_id, source_hash, model_name, refine_version, legacy_source_hash):
                skipped_count += 1
            else:
                pending_recipes.append(recipe_row)

        processed_count = 0
        refined_count = 0
        error_count = 0
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_refine_runs
                SET
                    status = 'running',
                    total_count = ?,
                    processed_count = ?,
                    refined_count = ?,
                    skipped_count = ?,
                    error_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (len(pending_recipes), processed_count, refined_count, skipped_count, error_count, run_id),
            )
            connection.commit()

        for row in pending_recipes:
            with _job_lock:
                pause_requested = bool(_job_state["pause_requested"])

            if pause_requested:
                with get_connection() as connection:
                    connection.execute(
                        "UPDATE ai_refine_runs SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (run_id,),
                    )
                    connection.commit()
                return

            recipe_id = row["id"]
            source_hash = build_refinement_source_hash(dict(row))
            legacy_source_hash = row["source_hash"] or ""

            try:
                if _should_skip_recipe_refinement(recipe_id, source_hash or "", model_name, refine_version, legacy_source_hash):
                    skipped_count += 1
                else:
                    snapshot = _load_recipe_snapshot(recipe_id)
                    refined = _generate_refined_ingredients(snapshot, model_name, run_id=run_id)
                    with get_connection() as connection:
                        _store_refine_snapshot(
                            connection,
                            recipe_id=recipe_id,
                            run_id=run_id,
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
                                last_error,
                                last_raw_response
                            )
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, NULL, NULL)
                            ON CONFLICT(recipe_id) DO UPDATE SET
                                source_hash = excluded.source_hash,
                                model = excluded.model,
                                refine_version = excluded.refine_version,
                                refined_at = CURRENT_TIMESTAMP,
                                last_run_id = excluded.last_run_id,
                                last_error = NULL,
                                last_raw_response = NULL
                            """,
                            (recipe_id, source_hash, model_name, refine_version, run_id),
                        )
                        connection.commit()
                    refined_count += 1
            except Exception as error:
                error_count += 1
                raw_response = getattr(error, "raw_response", None)
                with get_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO recipe_ai_refine_state (
                            recipe_id,
                            source_hash,
                            model,
                            refine_version,
                            refined_at,
                            last_run_id,
                            last_error,
                            last_raw_response
                        )
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
                        ON CONFLICT(recipe_id) DO UPDATE SET
                            source_hash = excluded.source_hash,
                            model = excluded.model,
                            refine_version = excluded.refine_version,
                            refined_at = CURRENT_TIMESTAMP,
                            last_run_id = excluded.last_run_id,
                            last_error = excluded.last_error,
                            last_raw_response = excluded.last_raw_response
                        """,
                        (recipe_id, source_hash, model_name, refine_version, run_id, str(error), raw_response),
                    )
                    connection.commit()

            processed_count += 1
            with get_connection() as connection:
                connection.execute(
                    """
                    UPDATE ai_refine_runs
                    SET
                        status = 'running',
                        processed_count = ?,
                        refined_count = ?,
                        skipped_count = ?,
                        error_count = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (processed_count, refined_count, skipped_count, error_count, run_id),
                )
                connection.commit()

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_refine_runs
                SET
                    status = 'completed',
                    processed_count = total_count,
                    refined_count = ?,
                    skipped_count = ?,
                    error_count = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (refined_count, skipped_count, error_count, run_id),
            )
            connection.commit()
    except Exception as error:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_refine_runs
                SET
                    status = 'failed',
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
                """,
                (str(error), run_id),
            )
            connection.commit()
    finally:
        with _job_lock:
            _job_state["thread"] = None
            _job_state["pause_requested"] = False


def _load_latest_run(connection) -> Optional[Dict[str, Any]]:
    row = connection.execute(
        """
        SELECT
            id,
            model,
            status,
            total_count,
            processed_count,
            refined_count,
            skipped_count,
            error_count,
            refine_version,
            started_at,
            updated_at,
            completed_at,
            error_message
        FROM ai_refine_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row is not None else None


def _build_refine_version() -> str:
    payload = {
        "version": REFINE_PROMPT_VERSION,
        "target_fields": ["ingredients"],
        "rule": "keep only ingredient entities, split or mark optional items, never rewrite recipe text fields",
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_recipe_snapshot(recipe_id: int) -> Dict[str, Any]:
    with get_connection() as connection:
        recipe_row = connection.execute(
            """
            SELECT
                id,
                name,
                library_section,
                section_name,
                cuisine,
                sub_cuisine,
                ingredients_text,
                seasonings_text,
                steps_text,
                notes_text,
                source_reference,
                source_text
            FROM recipes
            WHERE id = ?
            """,
            (recipe_id,),
        ).fetchone()
        ingredient_rows = connection.execute(
            """
            SELECT i.normalized_name AS name, ri.amount, ri.unit, ri.remark
            FROM recipe_ingredients AS ri
            INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            ORDER BY ri.id
            """,
            (recipe_id,),
        ).fetchall()

    return {
        "id": recipe_row["id"],
        "name": recipe_row["name"] or "",
        "library_section": recipe_row["library_section"] or "",
        "section_name": recipe_row["section_name"] or "",
        "cuisine": recipe_row["cuisine"] or "",
        "sub_cuisine": recipe_row["sub_cuisine"] or "",
        "ingredients_text": recipe_row["ingredients_text"] or "",
        "seasonings_text": recipe_row["seasonings_text"] or "",
        "steps_text": recipe_row["steps_text"] or "",
        "notes_text": recipe_row["notes_text"] or "",
        "source_reference": recipe_row["source_reference"] or "",
        "source_text": recipe_row["source_text"] or "",
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


def _generate_refined_ingredients(
    recipe: Dict[str, Any],
    model_name: str,
    run_id: Optional[int] = None,
) -> Dict[str, Any]:
    compact_payload = {
        "name": recipe.get("name", ""),
        "library_section": recipe.get("library_section", ""),
        "section_name": recipe.get("section_name", ""),
        "ingredients_text": recipe.get("ingredients_text", ""),
        "seasonings_text": recipe.get("seasonings_text", ""),
    }
    prompt = "\n".join(
        [
            "/no_think",
            "Do not output thinking, analysis, explanation, or chain-of-thought.",
            "Output the final JSON object immediately.",
            "",
            "Extract only structured ingredient entities from the recipe.",
            "Only use ingredients_text and seasonings_text.",
            "Ignore cooking steps. Do not infer ingredients from dish name alone.",
            "Return JSON only. No prose, no markdown, no code fences.",
            "",
            "Rules:",
            "1. name must be a concrete ingredient entity that can be bought or clearly identified.",
            "2. Drop dish names, flavor descriptions, explanatory sentences, brand slogans, ratio notes, and punctuation fragments.",
            "3. For A/B, A or B, or A(also B), split into multiple ingredient items. Non-primary options use remark='可选'.",
            "4. For phrases like 可加A, 加A更好吃, 可放B, 也可用C, keep only the ingredient name and set remark='可选'.",
            "5. Do not invent ingredients that are not present in the source text.",
            "6. Do not translate Chinese ingredient names into English. Keep the source language.",
            "7. Never output placeholders such as ingredient1, ingredient2, anotheringredient, yetanotheringredient.",
            "8. Never output pure quantities such as 500g as ingredient names.",
            "9. For references such as 见牛肉词条, return no ingredient unless an actual ingredient name is present outside the reference.",
            "10. Follow the provided JSON schema exactly.",
            "",
            "JSON schema target:",
            json.dumps(INGREDIENT_JSON_SCHEMA, ensure_ascii=False),
            "",
            "Recipe payload:",
            json.dumps(compact_payload, ensure_ascii=False),
        ]
    )

    messages = [
        {
            "role": "system",
            "content": "/no_think\nYou are a strict ingredient extraction assistant. Output final valid JSON only. Never output thinking or analysis.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw_content = _call_ollama_chat(model_name, messages, response_format=INGREDIENT_JSON_SCHEMA)
    except Exception as error:
        create_ai_conversation_log(
            feature="import_refinement",
            stage="ingredient_refinement",
            model=model_name,
            request_messages=messages,
            status="error",
            run_id=run_id,
            recipe_id=recipe["id"],
            error_text=str(error),
            meta={"recipe_name": recipe["name"]},
        )
        raise

    create_ai_conversation_log(
        feature="import_refinement",
        stage="ingredient_refinement",
        model=model_name,
        request_messages=messages,
        status="success",
        run_id=run_id,
        recipe_id=recipe["id"],
        response_text=raw_content,
        meta={"recipe_name": recipe["name"]},
    )

    parse_error: Optional[Exception] = None
    ingredients: List[Dict[str, Optional[str]]] = []
    try:
        parsed = _extract_json_payload(raw_content)
        ingredients = _sanitize_refined_ingredients(parsed.get("ingredients"))
    except Exception as error:
        parse_error = error
    if ingredients:
        ingredients = _merge_sanitized_ingredients(
            ingredients,
            _fallback_ingredients_from_declared_source(recipe),
        )
    if not ingredients:
        ingredients = _fallback_ingredients_from_source(recipe)
    if not ingredients and (recipe["ingredients_text"] or recipe["ingredients"]):
        raise RefineGenerationError(
            "Model did not return usable ingredient entities"
            if parse_error is not None
            else "Model returned no usable ingredient entities",
            raw_response=raw_content,
        )
    return {"ingredients": ingredients}


def _normalize_ingredient_items(value: Any) -> List[Dict[str, Optional[str]]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Optional[str]]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        normalized.append(
            {
                "name": name,
                "amount": _normalize_optional_text(item.get("amount")),
                "unit": _normalize_optional_text(item.get("unit")),
                "remark": _normalize_optional_text(item.get("remark")),
            }
        )
    return normalized


def _normalize_optional_text(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _sanitize_refined_ingredients(value: Any) -> List[Dict[str, Optional[str]]]:
    normalized = _normalize_ingredient_items(value)
    return _dedupe_sanitized_ingredients(normalized)


def _dedupe_sanitized_ingredients(normalized: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    result: List[Dict[str, Optional[str]]] = []
    seen = set()

    for item in normalized:
        name, amount, unit, remark = _normalize_item_fields(
            item["name"] or "",
            item["amount"],
            item["unit"],
            item["remark"],
        )

        for split_name, split_amount, split_unit, split_remark in _split_choice_name(name, amount, unit, remark):
            clean_name = normalize_ingredient_name(split_name)
            if not clean_name or _should_drop_refined_name(clean_name):
                continue

            normalized_item = {
                "name": clean_name,
                "amount": split_amount,
                "unit": split_unit,
                "remark": _normalize_optional_text(split_remark),
            }
            dedupe_key = (
                normalized_item["name"],
                normalized_item["amount"] or "",
                normalized_item["unit"] or "",
                normalized_item["remark"] or "",
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            result.append(normalized_item)

    return result


def _merge_sanitized_ingredients(
    primary: List[Dict[str, Optional[str]]],
    secondary: List[Dict[str, Optional[str]]],
) -> List[Dict[str, Optional[str]]]:
    return _dedupe_sanitized_ingredients(primary + secondary)


def _fallback_ingredients_from_declared_source(recipe: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    source_text = (recipe.get("ingredients_text") or "").strip()
    if not source_text:
        return []

    parsed_items = parse_ingredients_text(_remove_section_headings(source_text))
    candidates = [
        {
            "name": item.get("normalized_name") or item.get("source_name") or "",
            "amount": item.get("amount"),
            "unit": item.get("unit"),
            "remark": item.get("remark"),
        }
        for item in parsed_items
        if item.get("normalized_name")
    ]
    return _sanitize_refined_ingredients(candidates)


def _fallback_ingredients_from_source(recipe: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    text = "，".join(
        part
        for part in [
            (recipe.get("ingredients_text") or "").strip(),
            (recipe.get("seasonings_text") or "").strip(),
        ]
        if part
    )
    text = _remove_section_headings(text)
    if not text:
        return []

    raw_parts = [part.strip() for part in FALLBACK_SPLIT_PATTERN.split(text) if part.strip()]
    if not raw_parts:
        raw_parts = [text]
    if len(raw_parts) > 48:
        return []

    candidates: List[Dict[str, Optional[str]]] = []
    for raw_part in raw_parts:
        cleaned_part = re.sub(r"[()??\[\]??].*?[()??\[\]??]?", "", raw_part).strip()
        if not cleaned_part:
            continue
        if len(cleaned_part) > 24:
            continue
        candidates.append({"name": cleaned_part, "amount": None, "unit": None, "remark": None})

    sanitized = _sanitize_refined_ingredients(candidates)
    if sanitized:
        return sanitized

    if len(raw_parts) == 1 and len(raw_parts[0]) <= 40 and FALLBACK_CHOICE_PATTERN.search(raw_parts[0]):
        return _sanitize_refined_ingredients(
            [{"name": raw_parts[0], "amount": None, "unit": None, "remark": None}]
        )

    return []


def _normalize_item_fields(
    name: str,
    amount: Optional[str],
    unit: Optional[str],
    remark: Optional[str],
) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    candidate = re.sub(r"\s+", "", name or "")
    candidate = re.sub(r"[()（）\[\]【】]", "", candidate)
    candidate = _strip_known_prefixes(candidate)
    candidate, amount, unit, remark = _repair_quantity_in_name(candidate, amount, unit, remark)
    candidate, amount, unit, remark = _extract_amount_from_name(candidate, amount, unit, remark)
    candidate = _extract_named_fragment(candidate)
    candidate = _strip_section_labels(candidate)
    return candidate, amount, unit, remark


def _repair_quantity_in_name(
    text: str,
    amount: Optional[str],
    unit: Optional[str],
    remark: Optional[str],
) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    candidate = re.sub(r"\s+", "", text or "")
    if not candidate or not any(char.isdigit() for char in candidate):
        return text, amount, unit, remark

    parsed_items = parse_ingredients_text(candidate)
    if len(parsed_items) != 1:
        return text, amount, unit, remark

    parsed = parsed_items[0]
    parsed_name = str(parsed.get("normalized_name") or "").strip()
    if not parsed_name or parsed_name == candidate or any(char.isdigit() for char in parsed_name):
        return text, amount, unit, remark
    if _should_drop_refined_name(parsed_name):
        return text, amount, unit, remark

    parsed_amount = _normalize_optional_text(parsed.get("amount"))
    parsed_unit = _normalize_optional_text(parsed.get("unit"))
    parsed_remark = _normalize_optional_text(parsed.get("remark"))
    parsed_unit, parsed_remark = _promote_unit_remark(parsed_unit, parsed_remark)
    if not (parsed_amount or parsed_unit or parsed_remark):
        return text, amount, unit, remark

    existing_quantity = _format_quantity(amount, unit)
    parsed_quantity = _format_quantity(parsed_amount, parsed_unit)
    merged_remark = _merge_remarks(parsed_remark, remark)
    if existing_quantity and existing_quantity != parsed_quantity:
        merged_remark = _merge_remarks(existing_quantity, merged_remark)

    return parsed_name, parsed_amount or amount, parsed_unit or unit, merged_remark


def _promote_unit_remark(unit: Optional[str], remark: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if unit or not remark:
        return unit, remark
    candidate = remark.strip()
    if candidate.lower() in REFINE_EXTRA_UNITS:
        return candidate, None
    return unit, remark


def _format_quantity(amount: Optional[str], unit: Optional[str]) -> Optional[str]:
    clean_amount = _normalize_optional_text(amount)
    clean_unit = _normalize_optional_text(unit)
    if not clean_amount and not clean_unit:
        return None
    return f"{clean_amount or ''}{clean_unit or ''}" or None


def _split_choice_name(
    name: str,
    amount: Optional[str],
    unit: Optional[str],
    remark: Optional[str],
) -> List[tuple[str, Optional[str], Optional[str], Optional[str]]]:
    candidate = re.sub(r"\s+", "", name or "")
    extracted_name, optional_remark = _extract_optional_ingredient_name(candidate, remark)
    extracted_name = _strip_section_labels(extracted_name)
    merged_remark = _merge_remarks(optional_remark, remark)

    if re.search(r"(?:/|／|\\|or|OR|或)", extracted_name):
        parts = [part for part in re.split(r"(?:/|／|\\|or|OR|或)", extracted_name) if part.strip()]
        split_items: List[tuple[str, Optional[str], Optional[str], Optional[str]]] = []
        for index, part in enumerate(parts):
            split_items.append(
                (
                    part.strip(),
                    amount,
                    unit,
                    None if index == 0 else _merge_remarks("可选", merged_remark),
                )
            )
        return split_items

    segmented = _segment_compound_name(extracted_name)
    if len(segmented) > 1:
        return [(part, amount, unit, merged_remark) for part in segmented]

    return [(extracted_name, amount, unit, merged_remark)]


def _strip_known_prefixes(text: str) -> str:
    candidate = text
    for prefix in BRAND_PREFIXES:
        if candidate.startswith(prefix) and len(candidate) > len(prefix):
            candidate = candidate[len(prefix) :]
            break
    for prefix in GENERIC_PREFIXES:
        if candidate.startswith(prefix) and len(candidate) > len(prefix):
            candidate = candidate[len(prefix) :]
            break
    return candidate


def _remove_section_headings(text: str) -> str:
    return SECTION_HEADING_PATTERN.sub("，", text or "")


def _strip_section_labels(text: str) -> str:
    candidate = text or ""
    changed = True
    while changed:
        changed = False
        for label in SECTION_LABELS:
            if label and label in candidate and candidate != label:
                candidate = candidate.replace(label, "")
                changed = True
    return candidate


def _extract_amount_from_name(
    text: str,
    amount: Optional[str],
    unit: Optional[str],
    remark: Optional[str],
) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    if amount or unit:
        return text, amount, unit, remark

    match = AMOUNT_IN_NAME_PATTERN.search(text)
    if not match:
        return text, amount, unit, remark

    new_name = match.group("prefix").strip()
    package_hint = ""
    package_match = PACKAGE_HINT_PATTERN.search(new_name)
    if package_match:
        package_hint = package_match.group(1)
        new_name = new_name[: -len(package_hint)].strip()

    merged_remark = _merge_remarks(package_hint or None, remark)
    return new_name, match.group("amount"), match.group("unit"), merged_remark


def _extract_named_fragment(text: str) -> str:
    if "用的" in text:
        text = text.split("用的", 1)[1]
    elif "用" in text and len(text.split("用", 1)[1]) >= 2:
        text = text.split("用", 1)[1]
    return text


def _segment_compound_name(text: str) -> List[str]:
    candidate = text.strip()
    results: List[str] = []
    remaining = candidate

    while remaining:
        matched = False
        for segment in sorted(INGREDIENT_SEGMENTS, key=len, reverse=True):
            if remaining.startswith(segment):
                results.append(segment)
                remaining = remaining[len(segment) :]
                matched = True
                break
        if not matched:
            return [candidate]

    return results if results else [candidate]


def _extract_optional_ingredient_name(name: str, remark: Optional[str]) -> tuple[str, Optional[str]]:
    candidate = name.strip(" ,，。；;:：()（）[]【】")
    for prefix in OPTIONAL_PREFIXES:
        if candidate.startswith(prefix) and len(candidate) > len(prefix):
            return candidate[len(prefix):].strip(), _merge_remarks("可选", remark)
    for suffix in OPTIONAL_SUFFIXES:
        if candidate.endswith(suffix) and len(candidate) > len(suffix):
            return candidate[: -len(suffix)].strip(), _merge_remarks("可选", remark)
    return candidate, remark


def _should_drop_refined_name(name: str) -> bool:
    compact = re.sub(r"\s+", "", name or "")
    if not compact:
        return True
    if len(compact) > 20:
        return True
    if compact in {"%", "％", "1"}:
        return True
    return any(hint in compact for hint in DROP_HINTS)


def _merge_remarks(primary: Optional[str], secondary: Optional[str]) -> Optional[str]:
    first = _normalize_optional_text(primary)
    second = _normalize_optional_text(secondary)
    if not first:
        return second
    if not second or second == first:
        return first
    if second in first:
        return first
    return f"{first} / {second}"


def _apply_refined_recipe(connection, recipe_id: int, refined: Dict[str, Any]) -> None:
    connection.execute(
        """
        UPDATE recipes
        SET updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (recipe_id,),
    )
    sync_recipe_ingredients_from_items(connection, recipe_id, refined["ingredients"])


def _store_refine_snapshot(
    connection,
    *,
    recipe_id: int,
    run_id: Optional[int],
    model_name: str,
    refine_version: str,
    before_ingredients: List[Dict[str, Any]],
    after_ingredients: List[Dict[str, Any]],
) -> None:
    connection.execute(
        """
        INSERT INTO recipe_refine_snapshots (
            recipe_id,
            run_id,
            model,
            refine_version,
            before_ingredients_json,
            after_ingredients_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            recipe_id,
            run_id,
            model_name,
            refine_version,
            json.dumps(before_ingredients, ensure_ascii=False),
            json.dumps(after_ingredients, ensure_ascii=False),
        ),
    )


def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.replace("json", "", 1).strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"ingredients": parsed}
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    last_payload: Optional[Dict[str, Any]] = None
    for index, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            last_payload = parsed
        elif isinstance(parsed, list):
            last_payload = {"ingredients": parsed}

    if last_payload is not None:
        return last_payload

    raise ValueError("JSON payload not found")
