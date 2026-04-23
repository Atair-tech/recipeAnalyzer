import hashlib
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional

from app.db.database import get_connection
from app.services.ai_log_service import create_ai_conversation_log
from app.services.ingredient_service import normalize_ingredient_name, sync_recipe_ingredients_from_items
from app.services.ollama_service import OLLAMA_DEFAULT_MODEL, _call_ollama_chat as _ollama_chat_impl


REFINE_PROMPT_VERSION = "import-refine-v3"

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
)
AMOUNT_IN_NAME_PATTERN = re.compile(r"(?P<prefix>.*?)(?P<amount>\d+(?:\.\d+)?)(?P<unit>g|kg|ml|mL|L|l|克|千克|毫升|公升)$", re.I)
PACKAGE_HINT_PATTERN = re.compile(r"(半包|半袋|一包|一袋|半盒|一盒)$")

_job_lock = threading.Lock()
_job_state = {
    "run_id": None,
    "thread": None,
    "pause_requested": False,
}


def _call_ollama_chat(model_name: str, messages: List[Dict[str, str]], max_attempts: int = 2) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _ollama_chat_impl(model_name, messages)
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


def _run_refine_job(run_id: int, model_name: str, refine_version: str) -> None:
    try:
        with get_connection() as connection:
            recipes = connection.execute(
                """
                SELECT id, source_hash
                FROM recipes
                WHERE record_kind = 'recipe'
                ORDER BY id
                """
            ).fetchall()
            current_run = connection.execute(
                """
                SELECT processed_count, refined_count, skipped_count, error_count
                FROM ai_refine_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()

        processed_count = current_run["processed_count"] if current_run else 0
        refined_count = current_run["refined_count"] if current_run else 0
        skipped_count = current_run["skipped_count"] if current_run else 0
        error_count = current_run["error_count"] if current_run else 0

        for row in recipes[processed_count:]:
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
            source_hash = row["source_hash"]

            try:
                with get_connection() as connection:
                    state_row = connection.execute(
                        """
                        SELECT source_hash, model, refine_version
                        FROM recipe_ai_refine_state
                        WHERE recipe_id = ?
                        """,
                        (recipe_id,),
                    ).fetchone()

                if (
                    state_row is not None
                    and state_row["source_hash"] == source_hash
                    and state_row["model"] == model_name
                    and state_row["refine_version"] == refine_version
                ):
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
                                last_error
                            )
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, NULL)
                            ON CONFLICT(recipe_id) DO UPDATE SET
                                source_hash = excluded.source_hash,
                                model = excluded.model,
                                refine_version = excluded.refine_version,
                                refined_at = CURRENT_TIMESTAMP,
                                last_run_id = excluded.last_run_id,
                                last_error = NULL
                            """,
                            (recipe_id, source_hash, model_name, refine_version, run_id),
                        )
                        connection.commit()
                    refined_count += 1
            except Exception as error:
                error_count += 1
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
                            last_error
                        )
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                        ON CONFLICT(recipe_id) DO UPDATE SET
                            source_hash = excluded.source_hash,
                            model = excluded.model,
                            refine_version = excluded.refine_version,
                            refined_at = CURRENT_TIMESTAMP,
                            last_run_id = excluded.last_run_id,
                            last_error = excluded.last_error
                        """,
                        (recipe_id, source_hash, model_name, refine_version, run_id, str(error)),
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
            SELECT i.name, ri.amount, ri.unit, ri.remark
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
    prompt = "\n".join(
        [
            "你负责精校菜谱中的结构化食材，只返回合法 JSON。",
            "不要改写 ingredients_text、seasonings_text、steps_text、notes_text。",
            "你只需要输出 ingredients 数组。",
            "",
            "严格规则：",
            "1. name 必须是可以单独采购或明确识别的食材本体。",
            "2. 不要输出成菜名、套餐名、口味描述、建议句、品牌宣传、比例说明、标点残片。",
            "3. 对于 A/B、A or B、A（也可用B），拆成多个 ingredient，非主选项 remark=可选。",
            "4. 对于 可加A、加A更好吃、可放B、也可用C，输出 name=A/B/C，remark=可选。",
            "5. 对于不是食材实体的内容，直接丢弃。",
            "6. 不要发明原文中不存在的信息。",
            "7. 只输出一个 JSON 对象，不要 Markdown，不要解释。",
            "",
            "JSON 格式：",
            '{"ingredients":[{"name":"","amount":"","unit":"","remark":""}]}',
            "",
            "菜谱信息：",
            json.dumps(recipe, ensure_ascii=False),
        ]
    )

    messages = [
        {"role": "system", "content": "你是严谨的菜谱结构化整理助手。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_content = _call_ollama_chat(model_name, messages)
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

    parsed = _extract_json_object(raw_content)
    ingredients = _sanitize_refined_ingredients(parsed.get("ingredients"))
    if not ingredients and (recipe["ingredients_text"] or recipe["ingredients"]):
        raise ValueError("Model returned no usable ingredient entities")
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


def _normalize_item_fields(
    name: str,
    amount: Optional[str],
    unit: Optional[str],
    remark: Optional[str],
) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    candidate = re.sub(r"\s+", "", name or "")
    candidate = re.sub(r"[()（）\[\]【】]", "", candidate)
    candidate = _strip_known_prefixes(candidate)
    candidate, amount, unit, remark = _extract_amount_from_name(candidate, amount, unit, remark)
    candidate = _extract_named_fragment(candidate)
    return candidate, amount, unit, remark


def _split_choice_name(
    name: str,
    amount: Optional[str],
    unit: Optional[str],
    remark: Optional[str],
) -> List[tuple[str, Optional[str], Optional[str], Optional[str]]]:
    candidate = re.sub(r"\s+", "", name or "")
    extracted_name, optional_remark = _extract_optional_ingredient_name(candidate, remark)
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


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.replace("json", "", 1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON object not found")

    return json.loads(cleaned[start : end + 1])
