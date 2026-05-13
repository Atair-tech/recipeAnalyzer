import hashlib
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from app.core.env import load_local_env
from app.db.database import get_connection
from app.services.ai_log_service import create_ai_conversation_log
from app.services.ollama_service import OLLAMA_DEFAULT_MODEL, _call_ollama_chat


load_local_env()

INGREDIENT_FILTER_PROMPT_VERSION = "ingredient-display-filter-v6"
INGREDIENT_FILTER_BATCH_SIZE = 12

PROVIDER_DEEPSEEK = "deepseek_api"
PROVIDER_OLLAMA = "ollama"
DEFAULT_PROVIDER = os.getenv("RECIPE_ANALYZER_INGREDIENT_FILTER_PROVIDER", PROVIDER_DEEPSEEK).strip() or PROVIDER_DEEPSEEK

DEEPSEEK_BASE_URL = os.getenv("RECIPE_ANALYZER_DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_DEFAULT_MODEL = os.getenv("RECIPE_ANALYZER_DEEPSEEK_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
DEEPSEEK_REASONING_EFFORT = os.getenv("RECIPE_ANALYZER_DEEPSEEK_REASONING_EFFORT", "high").strip()
DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv("RECIPE_ANALYZER_DEEPSEEK_TIMEOUT", "300"))

DISPLAY_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "is_visible": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["is_visible", "reason"],
    "additionalProperties": False,
}

DISPLAY_FILTER_BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "is_visible": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "is_visible", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_job_lock = threading.Lock()
_job_state = {
    "run_id": None,
    "thread": None,
    "pause_requested": False,
}

_NOISE_PATTERNS = (
    r"^\s*[%*+/=]+\s*$",
    r"^\s*\d+(?:\.\d+)?\s*$",
    r"^\s*[*#]{2,}.*$",
    r".*含水量.*",
    r".*正常来说.*",
    r".*更好吃.*",
    r".*建议.*",
    r".*推荐.*",
    r".*必选.*",
    r".*尽量.*",
    r".*口味.*",
    r".*经典.*",
    r".*低卡.*",
    r".*冰箱剩菜.*",
    r".*丰富口感.*",
    r".*可泡发.*",
    r".*可以单独.*",
)

_NOISE_SUBSTRINGS = (
    "正常版",
    "原版",
    "配菜：",
    "锅底",
    "加到",
    "可加",
    "可放",
    "也好吃",
    "皆可",
    "最常见",
    "最常用",
)

_CATEGORY_PREFIXES = (
    "鸡肉：",
    "牛肉：",
    "猪肉：",
    "海鲜：",
    "风味类：",
    "干货类：",
    "香草类：",
    "配菜：",
    "必选：",
    "强推：",
)


def get_ingredient_filter_status() -> Dict[str, Any]:
    with get_connection() as connection:
        run = _load_latest_run(connection)

    with _job_lock:
        is_running = bool(_job_state["thread"] and _job_state["thread"].is_alive())
        pause_requested = bool(_job_state["pause_requested"])

    return {
        "run": run,
        "is_running": is_running,
        "pause_requested": pause_requested,
        "available_providers": [
            {"id": PROVIDER_DEEPSEEK, "label": "DeepSeek API（默认）", "default_model": DEEPSEEK_DEFAULT_MODEL},
            {"id": PROVIDER_OLLAMA, "label": "本地 Ollama（备选）", "default_model": OLLAMA_DEFAULT_MODEL},
        ],
        "deepseek_api_key_configured": bool(_get_deepseek_api_key()),
        "deepseek_api_key_source": _get_deepseek_api_key_source(),
    }


def start_ingredient_filter_run(model: Optional[str] = None, provider: Optional[str] = None) -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("An ingredient visibility run is already in progress")

    provider_name = _normalize_provider(provider)
    actual_model = _resolve_default_model(provider_name, model)
    model_identifier = _encode_model_identifier(provider_name, actual_model)
    filter_version = _build_filter_version(provider_name, actual_model)

    with get_connection() as connection:
        total_count = connection.execute("SELECT COUNT(*) FROM ingredients").fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO ai_ingredient_filter_runs (
                model,
                status,
                total_count,
                filter_version,
                started_at,
                updated_at
            )
            VALUES (?, 'running', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (model_identifier, total_count, filter_version),
        )
        run_id = cursor.lastrowid
        connection.commit()

    thread = threading.Thread(
        target=_run_ingredient_filter_job,
        args=(run_id, provider_name, actual_model, model_identifier, filter_version),
        daemon=True,
        name=f"ingredient-filter-{run_id}",
    )
    with _job_lock:
        _job_state["run_id"] = run_id
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_ingredient_filter_status()


def pause_ingredient_filter_run() -> Dict[str, Any]:
    with _job_lock:
        if not (_job_state["thread"] and _job_state["thread"].is_alive()):
            return get_ingredient_filter_status()
        _job_state["pause_requested"] = True
    return get_ingredient_filter_status()


def resume_ingredient_filter_run() -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("An ingredient visibility run is already in progress")

    with get_connection() as connection:
        run = connection.execute(
            """
            SELECT id, model, filter_version, status
            FROM ai_ingredient_filter_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if run is None or run["status"] != "paused":
        raise ValueError("No paused ingredient visibility run available")

    provider_name, actual_model = _decode_model_identifier(run["model"])
    thread = threading.Thread(
        target=_run_ingredient_filter_job,
        args=(run["id"], provider_name, actual_model, run["model"], run["filter_version"]),
        daemon=True,
        name=f"ingredient-filter-{run['id']}",
    )
    with _job_lock:
        _job_state["run_id"] = run["id"]
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_ingredient_filter_status()


def _run_ingredient_filter_job(
    run_id: int,
    provider_name: str,
    actual_model: str,
    model_identifier: str,
    filter_version: str,
) -> None:
    try:
        ingredients, current_run = _load_run_inputs(run_id)
        processed_count = current_run["processed_count"] if current_run else 0
        kept_count = current_run["kept_count"] if current_run else 0
        hidden_count = current_run["hidden_count"] if current_run else 0
        skipped_count = current_run["skipped_count"] if current_run else 0
        error_count = current_run["error_count"] if current_run else 0

        pending_items: List[Dict[str, Any]] = []

        for row in ingredients[processed_count:]:
            if _is_pause_requested():
                _mark_run_paused(run_id)
                return

            item = _row_to_item(row)
            state_row = _load_item_state(item["id"])
            if _can_skip_item(state_row, item["source_hash"], model_identifier, filter_version):
                skipped_count += 1
                processed_count += 1
                _update_run_progress(run_id, processed_count, kept_count, hidden_count, skipped_count, error_count)
                continue

            if provider_name == PROVIDER_OLLAMA:
                result = _deterministic_visibility_result(item)
                if result is not None:
                    _persist_filter_success(
                        item=item,
                        result=result,
                        model_identifier=model_identifier,
                        filter_version=filter_version,
                        run_id=run_id,
                    )
                    if result["is_visible"]:
                        kept_count += 1
                    else:
                        hidden_count += 1
                    processed_count += 1
                    _update_run_progress(run_id, processed_count, kept_count, hidden_count, skipped_count, error_count)
                    continue

            pending_items.append(item)

        if pending_items:
            if _is_pause_requested():
                _mark_run_paused(run_id)
                return

            if provider_name == PROVIDER_DEEPSEEK:
                processed_count, kept_count, hidden_count, error_count = _classify_with_deepseek_or_fallback(
                    items=pending_items,
                    actual_model=actual_model,
                    model_identifier=model_identifier,
                    filter_version=filter_version,
                    run_id=run_id,
                    processed_count=processed_count,
                    kept_count=kept_count,
                    hidden_count=hidden_count,
                    skipped_count=skipped_count,
                    error_count=error_count,
                )
            else:
                processed_count, kept_count, hidden_count, error_count = _classify_with_local_batches(
                    items=pending_items,
                    actual_model=actual_model,
                    model_identifier=model_identifier,
                    filter_version=filter_version,
                    run_id=run_id,
                    processed_count=processed_count,
                    kept_count=kept_count,
                    hidden_count=hidden_count,
                    skipped_count=skipped_count,
                    error_count=error_count,
                )

        if _is_pause_requested():
            _mark_run_paused(run_id)
            return

        _mark_run_completed(run_id, kept_count, hidden_count, skipped_count, error_count)
    except Exception as error:
        _mark_run_failed(run_id, str(error))
    finally:
        with _job_lock:
            _job_state["thread"] = None
            _job_state["pause_requested"] = False


def _classify_with_deepseek_or_fallback(
    *,
    items: List[Dict[str, Any]],
    actual_model: str,
    model_identifier: str,
    filter_version: str,
    run_id: int,
    processed_count: int,
    kept_count: int,
    hidden_count: int,
    skipped_count: int,
    error_count: int,
) -> Tuple[int, int, int, int]:
    try:
        visible_ids = _classify_ingredient_visibility_all_deepseek(items, actual_model, run_id=run_id)
        for item in items:
            is_visible = item["id"] in visible_ids
            _persist_filter_success(
                item=item,
                result={
                    "is_visible": is_visible,
                    "reason": _deepseek_visibility_reason(item, is_visible),
                    "raw_response": None,
                },
                model_identifier=model_identifier,
                filter_version=filter_version,
                run_id=run_id,
            )
            if is_visible:
                kept_count += 1
            else:
                hidden_count += 1
            processed_count += 1
        _update_run_progress(run_id, processed_count, kept_count, hidden_count, skipped_count, error_count)
        return processed_count, kept_count, hidden_count, error_count
    except Exception as error:
        _append_run_error(run_id, f"DeepSeek failed; local fallback started: {error}")
        fallback_identifier = _encode_model_identifier(PROVIDER_OLLAMA, OLLAMA_DEFAULT_MODEL)
        return _classify_with_local_batches(
            items=items,
            actual_model=OLLAMA_DEFAULT_MODEL,
            model_identifier=fallback_identifier,
            filter_version=_build_filter_version(PROVIDER_OLLAMA, OLLAMA_DEFAULT_MODEL),
            run_id=run_id,
            processed_count=processed_count,
            kept_count=kept_count,
            hidden_count=hidden_count,
            skipped_count=skipped_count,
            error_count=error_count,
        )


def _deepseek_visibility_reason(item: Dict[str, Any], is_visible: bool) -> str:
    if _hard_hide_visibility_item(item):
        return "Local safety rule hid this item after DeepSeek response"
    if _hard_keep_visibility_item(item):
        return "Local safety rule kept this compact ingredient alternative"
    return "DeepSeek returned this id as visible" if is_visible else "DeepSeek omitted this id"


def _classify_with_local_batches(
    *,
    items: List[Dict[str, Any]],
    actual_model: str,
    model_identifier: str,
    filter_version: str,
    run_id: int,
    processed_count: int,
    kept_count: int,
    hidden_count: int,
    skipped_count: int,
    error_count: int,
) -> Tuple[int, int, int, int]:
    for batch_start in range(0, len(items), INGREDIENT_FILTER_BATCH_SIZE):
        if _is_pause_requested():
            _mark_run_paused(run_id)
            return processed_count, kept_count, hidden_count, error_count

        batch = items[batch_start : batch_start + INGREDIENT_FILTER_BATCH_SIZE]
        try:
            results = _classify_ingredient_visibility_batch_local(batch, actual_model, run_id=run_id)
        except Exception as error:
            results = {}
            batch_error = error
        else:
            batch_error = None

        for item in batch:
            result = results.get(item["id"])
            if result is None:
                _persist_filter_error(
                    item=item,
                    model_identifier=model_identifier,
                    filter_version=filter_version,
                    run_id=run_id,
                    error=batch_error or ValueError("Local batch response missing item result"),
                )
                error_count += 1
            else:
                _persist_filter_success(
                    item=item,
                    result=result,
                    model_identifier=model_identifier,
                    filter_version=filter_version,
                    run_id=run_id,
                )
                if result["is_visible"]:
                    kept_count += 1
                else:
                    hidden_count += 1
            processed_count += 1
        _update_run_progress(run_id, processed_count, kept_count, hidden_count, skipped_count, error_count)

    return processed_count, kept_count, hidden_count, error_count


def _classify_ingredient_visibility_all_deepseek(
    ingredients: List[Dict[str, Any]],
    model_name: str,
    run_id: Optional[int] = None,
) -> Set[int]:
    api_key = _get_deepseek_api_key()
    if not api_key:
        raise ValueError("DeepSeek API key is not configured")

    items_payload = [
        {
            "id": item["id"],
            "text": item["normalized_name"],
        }
        for item in ingredients
    ]
    prompt = "\n".join(
        [
            "Return JSON only.",
            "Task: clean an ingredient dictionary for end-user UI display.",
            "Input contains only ingredient candidate strings. It contains no dish names, recipes, cooking steps, or notes.",
            "Keep only entries that are clean standalone ingredients, condiments, spices, sauces, edible products, or compact ingredient alternatives users can understand in a dropdown.",
            "Hide anything that is not itself a clean ingredient label.",
            "Hard-hide examples: '%以上含水量', '%水', '**正常来说', '正常来说', '但别太少了', '但别放太多', '10g丁香鱼配约100g卷心菜', '一人份大概75-80g面粉搭配90-100g土豆'.",
            "Hide strings containing amounts, units, ratios, percentages, serving notes, cooking notes, markdown markers, category prefixes, process verbs, or pairing phrases.",
            "Hide strings that should be split into multiple ingredients instead of shown as one dropdown item, especially patterns like '10g A 配约 100g B', 'A 搭配 B', 'A 加 B', or sentences containing more than one ingredient with quantities.",
            "Hide incomplete bracket fragments, broken punctuation, generic words, explanatory phrases, recommendation text, and non-ingredient descriptions.",
            "Keep compact alternatives only when every segment is a clean ingredient name, such as '羊肉/牛肉' or '春笋/冬笋'.",
            "Be conservative. If uncertain, do not include the item.",
            "Return only ids that should remain visible.",
            "",
            "Required JSON format:",
            '{"visible_ids":[1,2,3]}',
            "",
            "Items:",
            json.dumps(items_payload, ensure_ascii=False),
        ]
    )
    messages = [
        {
            "role": "system",
            "content": "Return valid JSON only. No prose. No markdown. No code fence.",
        },
        {"role": "user", "content": prompt},
    ]
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": 64000,
        "stream": False,
    }
    if DEEPSEEK_REASONING_EFFORT:
        payload["reasoning_effort"] = DEEPSEEK_REASONING_EFFORT

    try:
        with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS, trust_env=False) as client:
            response = client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        message = ((body.get("choices") or [{}])[0].get("message") or {})
        content = (message.get("content") or "").strip()
        if not content:
            raise ValueError("DeepSeek returned empty content")
        parsed = _extract_json_payload(content)
        visible_ids = parsed.get("visible_ids")
        if not isinstance(visible_ids, list):
            raise ValueError("DeepSeek JSON missing visible_ids")
        valid_item_ids = {item["id"] for item in ingredients}
        raw_result = {int(item_id) for item_id in visible_ids if isinstance(item_id, int) and int(item_id) in valid_item_ids}
        safety_hidden_ids = {
            item["id"]
            for item in ingredients
            if _hard_hide_visibility_item(item)
        }
        safety_visible_ids = {
            item["id"]
            for item in ingredients
            if item["id"] not in safety_hidden_ids and _hard_keep_visibility_item(item)
        }
        result = (raw_result - safety_hidden_ids) | safety_visible_ids
        create_ai_conversation_log(
            feature="ingredient_visibility_filter",
            stage="classify_all_deepseek",
            model=model_name,
            request_messages=messages,
            status="success",
            run_id=run_id,
            response_text=content,
            meta={"item_count": len(items_payload), "provider": PROVIDER_DEEPSEEK},
        )
        return result
    except Exception as error:
        create_ai_conversation_log(
            feature="ingredient_visibility_filter",
            stage="classify_all_deepseek",
            model=model_name,
            request_messages=messages,
            status="error",
            run_id=run_id,
            error_text=str(error),
            meta={"item_count": len(items_payload), "provider": PROVIDER_DEEPSEEK},
        )
        raise


def _classify_ingredient_visibility_batch_local(
    ingredients: List[Dict[str, Any]],
    model_name: str,
    run_id: Optional[int] = None,
) -> Dict[int, Dict[str, Any]]:
    if len(ingredients) == 1:
        single = ingredients[0]
        return {single["id"]: _classify_ingredient_visibility_single_local(single, model_name, run_id=run_id)}

    prompt = "\n".join(
        [
            "Classify whether each ingredient-like entry should be visible in end-user UI menus and summary counts.",
            "Be conservative: if an entry looks noisy, fragmented, process-like, or not display-safe, set is_visible=false.",
            "Prefer hiding weird entries over showing them.",
            "Keep concrete ingredient entities and compact candidate choices such as 羊肉/牛肉.",
            "Hide category-prefixed fragments, explanatory phrases, percentages, leftover notes, cooking notes, and broken bracket text.",
            "Return JSON only and follow the schema exactly.",
            "",
            "Schema:",
            json.dumps(DISPLAY_FILTER_BATCH_SCHEMA, ensure_ascii=False),
            "",
            "Items:",
            json.dumps(
                [
                    {
                        "id": item["id"],
                        "normalized_name": item["normalized_name"],
                    }
                    for item in ingredients
                ],
                ensure_ascii=False,
            ),
        ]
    )
    messages = [
        {
            "role": "system",
            "content": "You classify ingredient dictionary entries for UI visibility. Return valid JSON only. No prose, no markdown, no code fences.",
        },
        {"role": "user", "content": prompt},
    ]

    raw_content = _call_ollama_chat(model_name, messages, response_format=DISPLAY_FILTER_BATCH_SCHEMA)
    parsed = _normalize_batch_payload(_extract_json_payload(raw_content))
    items = parsed.get("items") or []
    results = {
        int(entry["id"]): {
            "is_visible": bool(entry.get("is_visible")),
            "reason": str(entry.get("reason") or "").strip() or "AI classified",
            "raw_response": raw_content,
        }
        for entry in items
        if entry.get("id") is not None
    }
    create_ai_conversation_log(
        feature="ingredient_visibility_filter",
        stage="classify_batch_local",
        model=model_name,
        request_messages=messages,
        status="success",
        run_id=run_id,
        response_text=raw_content,
        meta={"ingredient_ids": [item["id"] for item in ingredients], "provider": PROVIDER_OLLAMA},
    )
    return results


def _classify_ingredient_visibility_single_local(
    ingredient: Dict[str, Any],
    model_name: str,
    run_id: Optional[int] = None,
) -> Dict[str, Any]:
    prompt = "\n".join(
        [
            "Decide whether this ingredient-like text should be visible in end-user UI menus and counts.",
            "Be conservative: if uncertain, set is_visible=false.",
            "Keep only concrete ingredient entities and display-safe compact candidate options.",
            "Hide percentages, fragments, sentences, process notes, category prefixes, and broken text.",
            "Return JSON only and follow the schema exactly.",
            "",
            "Schema:",
            json.dumps(DISPLAY_FILTER_SCHEMA, ensure_ascii=False),
            "",
            "Ingredient payload:",
            json.dumps(
                {
                    "id": ingredient["id"],
                    "normalized_name": ingredient["normalized_name"],
                },
                ensure_ascii=False,
            ),
        ]
    )
    messages = [
        {
            "role": "system",
            "content": "Return valid JSON only. No prose, no markdown, no code fences.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        raw_content = _call_ollama_chat(model_name, messages, response_format=DISPLAY_FILTER_SCHEMA)
    except Exception as error:
        create_ai_conversation_log(
            feature="ingredient_visibility_filter",
            stage="classify_single_local",
            model=model_name,
            request_messages=messages,
            status="error",
            run_id=run_id,
            error_text=str(error),
            meta={"ingredient_id": ingredient["id"], "ingredient_name": ingredient["normalized_name"], "provider": PROVIDER_OLLAMA},
        )
        raise

    create_ai_conversation_log(
        feature="ingredient_visibility_filter",
        stage="classify_single_local",
        model=model_name,
        request_messages=messages,
        status="success",
        run_id=run_id,
        response_text=raw_content,
        meta={"ingredient_id": ingredient["id"], "ingredient_name": ingredient["normalized_name"], "provider": PROVIDER_OLLAMA},
    )

    parsed = _extract_json_payload(raw_content)
    return {
        "is_visible": bool(parsed.get("is_visible")),
        "reason": str(parsed.get("reason") or "").strip() or "AI classified",
        "raw_response": raw_content,
    }


def _load_run_inputs(run_id: int):
    with get_connection() as connection:
        ingredients = connection.execute(
            """
            SELECT id, normalized_name, is_visible
            FROM ingredients
            ORDER BY id
            """
        ).fetchall()
        current_run = connection.execute(
            """
            SELECT processed_count, kept_count, hidden_count, skipped_count, error_count
            FROM ai_ingredient_filter_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
    return ingredients, current_run


def _get_deepseek_api_key() -> str:
    return (os.getenv("RECIPE_ANALYZER_DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip()


def _get_deepseek_api_key_source() -> Optional[str]:
    if (os.getenv("RECIPE_ANALYZER_DEEPSEEK_API_KEY") or "").strip():
        return "RECIPE_ANALYZER_DEEPSEEK_API_KEY"
    if (os.getenv("DEEPSEEK_API_KEY") or "").strip():
        return "DEEPSEEK_API_KEY"
    return None


def _row_to_item(row: Any) -> Dict[str, Any]:
    item = {
        "id": row["id"],
        "normalized_name": row["normalized_name"] or "",
        "current_is_visible": row["is_visible"],
    }
    item["source_hash"] = _build_source_hash(item)
    return item


def _load_item_state(ingredient_id: int):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT source_hash, model, filter_version, last_error
            FROM ingredient_ai_filter_state
            WHERE ingredient_id = ?
            """,
            (ingredient_id,),
        ).fetchone()


def _can_skip_item(state_row: Any, source_hash: str, model_identifier: str, filter_version: str) -> bool:
    return (
        state_row is not None
        and state_row["source_hash"] == source_hash
        and state_row["model"] == model_identifier
        and state_row["filter_version"] == filter_version
        and not (state_row["last_error"] or "").strip()
    )


def _load_latest_run(connection) -> Optional[Dict[str, Any]]:
    row = connection.execute(
        """
        SELECT
            id,
            model,
            status,
            total_count,
            processed_count,
            kept_count,
            hidden_count,
            skipped_count,
            error_count,
            filter_version,
            started_at,
            updated_at,
            completed_at,
            error_message
        FROM ai_ingredient_filter_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return _serialize_run(row) if row is not None else None


def _serialize_run(row: Any) -> Dict[str, Any]:
    run = dict(row)
    provider_name, actual_model = _decode_model_identifier(run["model"])
    run["provider"] = provider_name
    run["model_name"] = actual_model
    run["model"] = actual_model
    return run


def _normalize_provider(provider: Optional[str]) -> str:
    value = (provider or DEFAULT_PROVIDER).strip().lower()
    if value in {"deepseek", "api", "deepseek-reasoner"}:
        return PROVIDER_DEEPSEEK
    if value in {"local"}:
        return PROVIDER_OLLAMA
    if value not in {PROVIDER_DEEPSEEK, PROVIDER_OLLAMA}:
        raise ValueError("Unsupported ingredient filter provider")
    return value


def _resolve_default_model(provider_name: str, model: Optional[str]) -> str:
    if model and model.strip():
        return model.strip()
    if provider_name == PROVIDER_DEEPSEEK:
        return DEEPSEEK_DEFAULT_MODEL
    return OLLAMA_DEFAULT_MODEL


def _encode_model_identifier(provider_name: str, actual_model: str) -> str:
    return f"{provider_name}:{actual_model}"


def _decode_model_identifier(model_identifier: str) -> Tuple[str, str]:
    if not model_identifier:
        return PROVIDER_OLLAMA, OLLAMA_DEFAULT_MODEL
    if model_identifier.startswith(f"{PROVIDER_DEEPSEEK}:"):
        return PROVIDER_DEEPSEEK, model_identifier.split(":", 1)[1]
    if model_identifier.startswith(f"{PROVIDER_OLLAMA}:"):
        return PROVIDER_OLLAMA, model_identifier.split(":", 1)[1]
    if model_identifier.startswith("deepseek-"):
        return PROVIDER_DEEPSEEK, model_identifier
    return PROVIDER_OLLAMA, model_identifier


def _build_filter_version(provider_name: str, actual_model: str) -> str:
    payload = {
        "version": INGREDIENT_FILTER_PROMPT_VERSION,
        "provider": provider_name,
        "model": actual_model,
        "mode": "deepseek-all-candidates" if provider_name == PROVIDER_DEEPSEEK else "ollama-batch",
        "batch_size": INGREDIENT_FILTER_BATCH_SIZE,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _build_source_hash(row: Dict[str, Any]) -> str:
    payload = {
        "normalized_name": row.get("normalized_name") or "",
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _deterministic_visibility_result(ingredient: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    candidate = (ingredient.get("normalized_name") or "").strip()
    compact = re.sub(r"\s+", "", candidate)
    if not compact:
        return {"is_visible": False, "reason": "empty ingredient entry", "raw_response": ""}

    if any(re.search(pattern, compact, flags=re.I) for pattern in _NOISE_PATTERNS):
        return {"is_visible": False, "reason": "deterministic noise pattern", "raw_response": ""}

    if any(marker in compact for marker in _NOISE_SUBSTRINGS):
        return {"is_visible": False, "reason": "deterministic phrase noise", "raw_response": ""}

    if any(compact.startswith(prefix) for prefix in _CATEGORY_PREFIXES):
        return {"is_visible": False, "reason": "deterministic category-prefixed fragment", "raw_response": ""}

    if _looks_like_broken_bracket_text(compact):
        return {"is_visible": False, "reason": "deterministic broken bracket fragment", "raw_response": ""}

    option_tokens = _parse_option_tokens(compact)
    if option_tokens and all(_looks_like_concrete_ingredient(token) for token in option_tokens):
        return {"is_visible": True, "reason": "deterministic compact candidate options", "raw_response": ""}

    if _looks_like_concrete_ingredient(compact):
        return {"is_visible": True, "reason": "deterministic concrete ingredient", "raw_response": ""}

    if compact.lower() in {"powder", "water", "sauce", "broth", "seasoning"}:
        return {"is_visible": False, "reason": "deterministic generic english fragment", "raw_response": ""}

    return None


def _hard_hide_visibility_item(ingredient: Dict[str, Any]) -> bool:
    candidate = (ingredient.get("normalized_name") or "").strip()
    compact = re.sub(r"\s+", "", candidate)
    if not compact:
        return True

    if any(re.search(pattern, compact, flags=re.I) for pattern in _NOISE_PATTERNS):
        return True
    if _looks_like_broken_bracket_text(compact):
        return True

    hard_markers = (
        "**",
        "%",
        "含水量",
        "正常来说",
        "正常",
        "但别",
        "但放",
        "但加",
        "推荐",
        "建议",
        "首推",
        "强推",
        "记录",
        "合计",
        "一人份",
        "大概",
        "左右",
        "以上",
        "以下",
        "约",
        "可加",
        "可放",
        "如想",
        "比如",
        "用量",
        "配约",
        "搭配",
        "更好吃",
        "不减脂",
        "口味选择",
        "料头",
    )
    if any(marker in compact for marker in hard_markers):
        return True

    if re.search(r"\d+(?:\.\d+)?(?:g|kg|克|斤|ml|毫升|勺|个|只|根|片|份|碗|杯|包)", compact, flags=re.I):
        return True
    if re.search(r"(?:配|搭配|加|放|加入|放入).*\d", compact):
        return True
    if re.search(r"\d.*(?:配|搭配|加|放|加入|放入)", compact):
        return True

    option_tokens = _parse_option_tokens(compact)
    if option_tokens:
        return not all(_looks_like_concrete_ingredient(token) for token in option_tokens)

    if len(compact) > 14 and re.search(r"(配|搭配|加|放|用|为主|可省|皆可|等等|等)", compact):
        return True

    return False


def _hard_keep_visibility_item(ingredient: Dict[str, Any]) -> bool:
    candidate = (ingredient.get("normalized_name") or "").strip()
    compact = re.sub(r"\s+", "", candidate)
    option_tokens = _parse_option_tokens(compact)
    if option_tokens:
        return all(_looks_like_concrete_ingredient(token) for token in option_tokens)
    return False


def _parse_option_tokens(text: str) -> Optional[List[str]]:
    normalized = re.sub(r"\s+", "", text)
    normalized = re.sub(r"(?i)\bor\b", "/", normalized)
    normalized = normalized.replace("或", "/")
    if "/" not in normalized:
        return None
    tokens = [token.strip("()（）[]【】,，:：") for token in normalized.split("/") if token.strip()]
    if len(tokens) < 2 or len(tokens) > 3:
        return None
    return tokens


def _looks_like_broken_bracket_text(text: str) -> bool:
    return (
        text.count("（") != text.count("）")
        or text.count("(") != text.count(")")
        or text.endswith(("（", "(", "，", ",", ":", "：", "-", "+"))
    )


def _looks_like_concrete_ingredient(text: str) -> bool:
    cleaned = text.strip("()（）[]【】,，:：")
    if not cleaned:
        return False
    if len(cleaned) > 12:
        return False
    if any(marker in cleaned for marker in ("建议", "推荐", "正常", "更好吃", "冰箱", "口味", "经典", "低卡")):
        return False
    if re.search(r"[%*#=]", cleaned):
        return False
    if re.search(r"\d{2,}", cleaned):
        return False
    if re.search(r"(加入|放入|加到|尽量|选择|做法|可泡发|常见|常用|丰富口感)", cleaned):
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9\-]+", cleaned))


def _normalize_batch_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, list):
        return {"items": payload}
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload
    raise ValueError("Batch JSON payload not found")


def _extract_json_payload(raw_text: str) -> Any:
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.replace("json", "", 1).strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    last_payload: Any = None
    for index, char in enumerate(cleaned):
        if char not in "{[":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            last_payload = parsed

    if last_payload is not None:
        return last_payload
    raise ValueError("JSON payload not found")


def _persist_filter_success(
    *,
    item: Dict[str, Any],
    result: Dict[str, Any],
    model_identifier: str,
    filter_version: str,
    run_id: int,
) -> None:
    is_visible = 1 if result["is_visible"] else 0
    with get_connection() as connection:
        connection.execute(
            "UPDATE ingredients SET is_visible = ? WHERE id = ?",
            (is_visible, item["id"]),
        )
        connection.execute(
            """
            INSERT INTO ingredient_ai_filter_state (
                ingredient_id,
                source_hash,
                model,
                filter_version,
                filtered_at,
                last_run_id,
                is_visible,
                reason,
                last_error,
                last_raw_response
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, NULL, ?)
            ON CONFLICT(ingredient_id) DO UPDATE SET
                source_hash = excluded.source_hash,
                model = excluded.model,
                filter_version = excluded.filter_version,
                filtered_at = CURRENT_TIMESTAMP,
                last_run_id = excluded.last_run_id,
                is_visible = excluded.is_visible,
                reason = excluded.reason,
                last_error = NULL,
                last_raw_response = excluded.last_raw_response
            """,
            (
                item["id"],
                item["source_hash"],
                model_identifier,
                filter_version,
                run_id,
                is_visible,
                result["reason"],
                result.get("raw_response"),
            ),
        )
        connection.commit()


def _persist_filter_error(
    *,
    item: Dict[str, Any],
    model_identifier: str,
    filter_version: str,
    run_id: int,
    error: Exception,
) -> None:
    raw_response = getattr(error, "raw_response", None)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ingredient_ai_filter_state (
                ingredient_id,
                source_hash,
                model,
                filter_version,
                filtered_at,
                last_run_id,
                is_visible,
                reason,
                last_error,
                last_raw_response
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, NULL, ?, ?)
            ON CONFLICT(ingredient_id) DO UPDATE SET
                source_hash = excluded.source_hash,
                model = excluded.model,
                filter_version = excluded.filter_version,
                filtered_at = CURRENT_TIMESTAMP,
                last_run_id = excluded.last_run_id,
                last_error = excluded.last_error,
                last_raw_response = excluded.last_raw_response
            """,
            (
                item["id"],
                item["source_hash"],
                model_identifier,
                filter_version,
                run_id,
                item["current_is_visible"],
                str(error),
                raw_response,
            ),
        )
        connection.commit()


def _update_run_progress(
    run_id: int,
    processed_count: int,
    kept_count: int,
    hidden_count: int,
    skipped_count: int,
    error_count: int,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE ai_ingredient_filter_runs
            SET
                status = 'running',
                processed_count = ?,
                kept_count = ?,
                hidden_count = ?,
                skipped_count = ?,
                error_count = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (processed_count, kept_count, hidden_count, skipped_count, error_count, run_id),
        )
        connection.commit()


def _append_run_error(run_id: int, message: str) -> None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT error_message FROM ai_ingredient_filter_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        current = (row["error_message"] if row else "") or ""
        next_value = f"{current}\n{message}".strip() if current else message
        connection.execute(
            """
            UPDATE ai_ingredient_filter_runs
            SET error_message = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (next_value[:4000], run_id),
        )
        connection.commit()


def _mark_run_paused(run_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE ai_ingredient_filter_runs
            SET status = 'paused', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (run_id,),
        )
        connection.commit()


def _mark_run_completed(
    run_id: int,
    kept_count: int,
    hidden_count: int,
    skipped_count: int,
    error_count: int,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE ai_ingredient_filter_runs
            SET
                status = 'completed',
                processed_count = total_count,
                kept_count = ?,
                hidden_count = ?,
                skipped_count = ?,
                error_count = ?,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (kept_count, hidden_count, skipped_count, error_count, run_id),
        )
        connection.commit()


def _mark_run_failed(run_id: int, error_message: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE ai_ingredient_filter_runs
            SET
                status = 'failed',
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP,
                error_message = ?
            WHERE id = ?
            """,
            (error_message, run_id),
        )
        connection.commit()


def _is_pause_requested() -> bool:
    with _job_lock:
        return bool(_job_state["pause_requested"])
