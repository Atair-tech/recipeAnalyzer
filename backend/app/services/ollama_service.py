import json
import os
import re
import time
from typing import Any, Dict, Generator, List, Optional

import httpx

from app.services.ai_log_service import create_ai_conversation_log
from app.services.deepseek_service import interpret_recipe_query_with_deepseek, rerank_recipe_candidates_with_deepseek
from app.services.library_context_service import format_library_vocabulary_summary, get_library_vocabulary_summary
from app.services.recipe_service import get_recipe
from app.services.search_service import natural_search


OLLAMA_BASE_URL = os.getenv("RECIPE_ANALYZER_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CONFIGURED_MODEL = os.getenv("RECIPE_ANALYZER_OLLAMA_MODEL", "").strip()
OLLAMA_DEFAULT_MODEL = OLLAMA_CONFIGURED_MODEL or "qwen3.5:4b"
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("RECIPE_ANALYZER_OLLAMA_TIMEOUT", "240"))
MAX_CONTEXT_ITEMS = 30
MAX_CONTEXT_TEXT_CHARS = 160
MAX_CONTEXT_STEPS_CHARS = 220

FAST_PATH_REPLIES = {
    "你好": "你好。可以直接问我菜谱、食材、做法、自动标签或筛选相关问题。",
    "您好": "你好。可以直接问我菜谱、食材、做法、自动标签或筛选相关问题。",
    "嗨": "你好。可以直接问我菜谱、食材、做法、自动标签或筛选相关问题。",
    "hello": "你好。可以直接问我菜谱、食材、做法、自动标签或筛选相关问题。",
    "hi": "你好。可以直接问我菜谱、食材、做法、自动标签或筛选相关问题。",
    "在吗": "在。你可以直接问我菜谱、食材、做法或筛选相关问题。",
    "谢谢": "不客气。",
    "多谢": "不客气。",
    "收到": "收到。",
    "好的": "好的。",
}


def _call_ollama_chat_logged(
    *,
    feature: str,
    stage: str,
    model: str,
    messages: List[Dict[str, str]],
    recipe_id: Optional[int] = None,
    run_id: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    try:
        response_text = _call_ollama_chat(model, messages)
    except Exception as error:
        create_ai_conversation_log(
            feature=feature,
            stage=stage,
            model=model,
            request_messages=messages,
            status="error",
            run_id=run_id,
            recipe_id=recipe_id,
            error_text=str(error),
            meta=meta,
        )
        raise

    create_ai_conversation_log(
        feature=feature,
        stage=stage,
        model=model,
        request_messages=messages,
        status="success",
        run_id=run_id,
        recipe_id=recipe_id,
        response_text=response_text,
        meta=meta,
    )
    return response_text


def get_ollama_status() -> Dict[str, Any]:
    try:
        models = list_ollama_models()
        default_model = _resolve_default_model_from_list(models)
        return {
            "available": True,
            "base_url": OLLAMA_BASE_URL,
            "default_model": default_model,
            "models": models,
            "error": None,
        }
    except Exception as error:
        return {
            "available": False,
            "base_url": OLLAMA_BASE_URL,
            "default_model": OLLAMA_DEFAULT_MODEL,
            "models": [],
            "error": str(error),
        }


def list_ollama_models() -> List[Dict[str, Any]]:
    with httpx.Client(timeout=OLLAMA_TIMEOUT_SECONDS, trust_env=False) as client:
        response = client.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        payload = response.json()

    return [
        {
            "name": item.get("name"),
            "size": item.get("size"),
            "modified_at": item.get("modified_at"),
        }
        for item in payload.get("models", [])
        if item.get("name")
    ]


def _resolve_default_model_from_list(models: List[Dict[str, Any]]) -> str:
    model_names = [item["name"] for item in models if item.get("name")]
    if OLLAMA_CONFIGURED_MODEL:
        return OLLAMA_CONFIGURED_MODEL
    if OLLAMA_DEFAULT_MODEL in model_names:
        return OLLAMA_DEFAULT_MODEL
    for preferred_model in ("qwen3.5:4b", "qwen3:4b", "qwen3:0.6b"):
        if preferred_model in model_names:
            return preferred_model
    return model_names[0] if model_names else OLLAMA_DEFAULT_MODEL


def ask_recipe_assistant(
    message: str,
    model: Optional[str] = None,
    selected_recipe_id: Optional[int] = None,
    top_k: int = 6,
    history: Optional[List[Dict[str, str]]] = None,
    use_deepseek_interpretation: bool = True,
    allow_external_rerank: bool = False,
) -> Dict[str, Any]:
    normalized_message = (message or "").strip()
    if not normalized_message:
        raise ValueError("Message is required")

    selected_recipe_id = None
    model_name = (model or OLLAMA_DEFAULT_MODEL).strip()
    requested_count = _extract_requested_count(normalized_message)
    safe_top_k = _resolve_context_limit(top_k, requested_count, allow_external_rerank)
    normalized_history = _normalize_history(history or [])
    selected_recipe = get_recipe(selected_recipe_id) if selected_recipe_id else None

    fast_path_reply = _match_fast_path_reply(normalized_message, selected_recipe_id, normalized_history)
    if fast_path_reply is not None:
        return {
            "message": normalized_message,
            "model": model_name,
            "selected_recipe_id": selected_recipe_id,
            "answer": fast_path_reply,
            "citations": [],
            "interpretation": {
                "intent": "闲聊短句",
                "concepts": [],
                "expanded_terms": [],
                "constraints": [],
                "retrieval_query": "",
                "notes": "本轮命中快路径，未进入检索增强流程。",
                "raw": "",
                "source": "fast_path",
            },
            "retrieval": {
                "query": "",
                "understanding": {},
                "items": [],
                "total": 0,
            },
            "pipeline": {
                "mode": "fast_path",
                "interpretation_ms": 0,
                "retrieval_ms": 0,
                "answer_ms": 0,
            },
        }

    route_started = time.perf_counter()
    route = _route_user_message(model_name, normalized_message, selected_recipe_id)
    route_elapsed_ms = int((time.perf_counter() - route_started) * 1000)
    if route["route"] != "recipe":
        return _answer_general_message(
            model_name=model_name,
            message=normalized_message,
            route=route,
            route_elapsed_ms=route_elapsed_ms,
        )

    interpretation_started = time.perf_counter()
    interpretation = _interpret_for_retrieval(
        model_name=model_name,
        message=normalized_message,
        use_deepseek_interpretation=use_deepseek_interpretation,
    )
    interpretation_elapsed_ms = int((time.perf_counter() - interpretation_started) * 1000)
    requested_count = requested_count or _safe_requested_count(interpretation.get("target_count"))
    safe_top_k = _resolve_context_limit(top_k, requested_count, allow_external_rerank)

    retrieval_query = _build_retrieval_query(normalized_message, interpretation)
    retrieval_extra_terms = interpretation.get("expanded_terms") or []

    retrieval_started = time.perf_counter()
    search_result = natural_search(
        retrieval_query,
        limit=safe_top_k,
        offset=0,
        extra_terms=retrieval_extra_terms,
        structured_understanding=interpretation,
    )
    context_items = _build_context_items(search_result.get("items", []), selected_recipe)
    external_rerank = _maybe_rerank_context_items(
        message=normalized_message,
        interpretation=interpretation,
        context_items=context_items,
        requested_count=requested_count,
        allow_external_rerank=allow_external_rerank,
    )
    if external_rerank.get("ranked_ids"):
        context_items = _apply_external_rerank(context_items, external_rerank)
    citations = _build_citations(context_items)
    retrieval_elapsed_ms = int((time.perf_counter() - retrieval_started) * 1000)

    answer_started = time.perf_counter()
    messages = _build_chat_messages(
        user_message=normalized_message,
        selected_recipe=selected_recipe,
        context_items=context_items,
        history=normalized_history,
        interpretation=interpretation,
        requested_count=requested_count,
    )
    answer = _call_ollama_chat_logged(
        feature="assistant_chat",
        stage="answer",
        model=model_name,
        messages=messages,
        recipe_id=selected_recipe_id,
        meta={
            "message": normalized_message,
            "top_k": safe_top_k,
            "requested_count": requested_count,
            "retrieval_query": retrieval_query,
        },
    )
    answer_elapsed_ms = int((time.perf_counter() - answer_started) * 1000)

    return {
        "message": normalized_message,
        "model": model_name,
        "selected_recipe_id": selected_recipe_id,
        "answer": answer,
        "citations": citations,
        "interpretation": interpretation,
        "retrieval": {
            "query": retrieval_query,
            "understanding": search_result.get("understanding", {}),
            "items": context_items,
            "total": len(context_items),
            "external_rerank": external_rerank,
        },
        "pipeline": {
            "mode": "retrieval_augmented",
            "route_ms": route_elapsed_ms,
            "interpretation_ms": interpretation_elapsed_ms,
            "retrieval_ms": retrieval_elapsed_ms,
            "answer_ms": answer_elapsed_ms,
        },
    }


def stream_recipe_assistant(
    message: str,
    model: Optional[str] = None,
    selected_recipe_id: Optional[int] = None,
    top_k: int = 6,
    history: Optional[List[Dict[str, str]]] = None,
    show_reasoning: bool = False,
    use_deepseek_interpretation: bool = True,
    allow_external_rerank: bool = False,
) -> Generator[str, None, None]:
    normalized_message = (message or "").strip()
    if not normalized_message:
        raise ValueError("Message is required")

    selected_recipe_id = None
    model_name = (model or OLLAMA_DEFAULT_MODEL).strip()
    requested_count = _extract_requested_count(normalized_message)
    safe_top_k = _resolve_context_limit(top_k, requested_count, allow_external_rerank)
    normalized_history = _normalize_history(history or [])
    selected_recipe = get_recipe(selected_recipe_id) if selected_recipe_id else None

    fast_path_reply = _match_fast_path_reply(normalized_message, selected_recipe_id, normalized_history)
    if fast_path_reply is not None:
        result = {
            "message": normalized_message,
            "model": model_name,
            "selected_recipe_id": selected_recipe_id,
            "answer": fast_path_reply,
            "citations": [],
            "interpretation": {
                "intent": "闲聊短句",
                "concepts": [],
                "expanded_terms": [],
                "constraints": [],
                "retrieval_query": "",
                "notes": "本轮命中快路径，未进入检索增强流程。",
                "raw": "",
                "source": "fast_path",
            },
            "retrieval": {"query": "", "understanding": {}, "items": [], "total": 0},
            "pipeline": {
                "mode": "fast_path",
                "interpretation_ms": 0,
                "retrieval_ms": 0,
                "answer_ms": 0,
            },
        }
        yield _encode_stream_event({"type": "stage", "stage": "fast_path"})
        yield _encode_stream_event({"type": "answer_chunk", "delta": fast_path_reply})
        yield _encode_stream_event({"type": "final", "result": result})
        return

    route_started = time.perf_counter()
    yield _encode_stream_event({"type": "stage", "stage": "routing"})
    route = _route_user_message(model_name, normalized_message, selected_recipe_id)
    route_elapsed_ms = int((time.perf_counter() - route_started) * 1000)
    if route["route"] != "recipe":
        yield from _stream_general_message(
            model_name=model_name,
            message=normalized_message,
            route=route,
            route_elapsed_ms=route_elapsed_ms,
            show_reasoning=show_reasoning,
        )
        return

    interpretation_started = time.perf_counter()
    yield _encode_stream_event(
        {
            "type": "stage",
            "stage": "external_interpretation" if use_deepseek_interpretation else "interpretation",
        }
    )
    interpretation = _interpret_for_retrieval(
        model_name=model_name,
        message=normalized_message,
        use_deepseek_interpretation=use_deepseek_interpretation,
    )
    interpretation_elapsed_ms = int((time.perf_counter() - interpretation_started) * 1000)
    requested_count = requested_count or _safe_requested_count(interpretation.get("target_count"))
    safe_top_k = _resolve_context_limit(top_k, requested_count, allow_external_rerank)
    yield _encode_stream_event({"type": "interpretation", "data": interpretation})

    retrieval_query = _build_retrieval_query(normalized_message, interpretation)
    retrieval_extra_terms = interpretation.get("expanded_terms") or []

    retrieval_started = time.perf_counter()
    yield _encode_stream_event({"type": "stage", "stage": "retrieval"})
    search_result = natural_search(
        retrieval_query,
        limit=safe_top_k,
        offset=0,
        extra_terms=retrieval_extra_terms,
        structured_understanding=interpretation,
    )
    context_items = _build_context_items(search_result.get("items", []), selected_recipe)
    if allow_external_rerank:
        yield _encode_stream_event({"type": "stage", "stage": "external_rerank"})
    external_rerank = _maybe_rerank_context_items(
        message=normalized_message,
        interpretation=interpretation,
        context_items=context_items,
        requested_count=requested_count,
        allow_external_rerank=allow_external_rerank,
    )
    if external_rerank.get("ranked_ids"):
        context_items = _apply_external_rerank(context_items, external_rerank)
    citations = _build_citations(context_items)
    retrieval_elapsed_ms = int((time.perf_counter() - retrieval_started) * 1000)
    retrieval_payload = {
        "query": retrieval_query,
        "understanding": search_result.get("understanding", {}),
        "items": context_items,
        "total": len(context_items),
        "external_rerank": external_rerank,
    }
    yield _encode_stream_event({"type": "retrieval", "data": retrieval_payload})

    answer_started = time.perf_counter()
    yield _encode_stream_event({"type": "stage", "stage": "answer"})
    messages = _build_chat_messages(
        user_message=normalized_message,
        selected_recipe=selected_recipe,
        context_items=context_items,
        history=normalized_history,
        interpretation=interpretation,
        requested_count=requested_count,
    )

    answer_parts: List[str] = []
    thinking_parts: List[str] = []
    try:
        for chunk in _stream_ollama_chat(model_name, messages, include_thinking=show_reasoning):
            if chunk["type"] == "answer_chunk":
                answer_parts.append(chunk["delta"])
            elif chunk["type"] == "thinking_chunk":
                thinking_parts.append(chunk["delta"])
            yield _encode_stream_event(chunk)
    except Exception as error:
        create_ai_conversation_log(
            feature="assistant_chat",
            stage="answer",
            model=model_name,
            request_messages=messages,
            status="error",
            recipe_id=selected_recipe_id,
            error_text=str(error),
            meta={
                "message": normalized_message,
                "top_k": safe_top_k,
                "requested_count": requested_count,
                "retrieval_query": retrieval_query,
                "stream": True,
            },
        )
        raise

    answer = "".join(answer_parts).strip()
    answer_elapsed_ms = int((time.perf_counter() - answer_started) * 1000)
    if not answer:
        raise RuntimeError("Ollama returned an empty response")

    if show_reasoning and thinking_parts:
        interpretation["raw_thinking"] = "".join(thinking_parts).strip()

    create_ai_conversation_log(
        feature="assistant_chat",
        stage="answer",
        model=model_name,
        request_messages=messages,
        status="success",
        recipe_id=selected_recipe_id,
        response_text=answer,
        meta={
            "message": normalized_message,
            "top_k": safe_top_k,
            "requested_count": requested_count,
            "retrieval_query": retrieval_query,
            "stream": True,
            "thinking": "".join(thinking_parts).strip() if thinking_parts else "",
        },
    )

    result = {
        "message": normalized_message,
        "model": model_name,
        "selected_recipe_id": selected_recipe_id,
        "answer": answer,
        "citations": citations,
        "interpretation": interpretation,
        "retrieval": retrieval_payload,
        "pipeline": {
            "mode": "retrieval_augmented",
            "route_ms": route_elapsed_ms,
            "interpretation_ms": interpretation_elapsed_ms,
            "retrieval_ms": retrieval_elapsed_ms,
            "answer_ms": answer_elapsed_ms,
        },
    }
    yield _encode_stream_event({"type": "final", "result": result})


def _match_fast_path_reply(
    message: str,
    selected_recipe_id: Optional[int],
    history: List[Dict[str, str]],
) -> Optional[str]:
    if selected_recipe_id:
        return None

    if history:
        return None

    normalized = re.sub(r"\s+", "", message.strip().lower())
    if not normalized:
        return None

    if normalized in FAST_PATH_REPLIES:
        return FAST_PATH_REPLIES[normalized]

    if len(normalized) <= 4 and normalized in {"ok", "oki", "ok啦"}:
        return "收到。"

    return None


def _extract_requested_count(message: str) -> Optional[int]:
    patterns = [
        r"(?:找|推荐|列出|给我|筛选|挑)(\d{1,2})(?:道|个|款|条)",
        r"(\d{1,2})(?:道|个|款|条)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            value = int(match.group(1))
            if 1 <= value <= 30:
                return value

    chinese_digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    match = re.search(r"(?:找|推荐|列出|给我|筛选|挑)?([一二两三四五六七八九十]{1,3})(?:道|个|款|条)", message)
    if not match:
        return None
    token = match.group(1)
    if token == "十":
        return 10
    if token.startswith("十") and len(token) == 2:
        return 10 + chinese_digits.get(token[1], 0)
    if token.endswith("十") and len(token) == 2:
        return chinese_digits.get(token[0], 0) * 10
    if "十" in token and len(token) == 3:
        return chinese_digits.get(token[0], 0) * 10 + chinese_digits.get(token[2], 0)
    return chinese_digits.get(token)


def _resolve_context_limit(top_k: int, requested_count: Optional[int], allow_external_rerank: bool = False) -> int:
    configured_limit = max(1, min(int(top_k), MAX_CONTEXT_ITEMS))
    if allow_external_rerank:
        if requested_count:
            return max(configured_limit, min(MAX_CONTEXT_ITEMS, requested_count * 5))
        return max(configured_limit, min(MAX_CONTEXT_ITEMS, configured_limit * 2))
    if not requested_count:
        return configured_limit
    return max(configured_limit, min(MAX_CONTEXT_ITEMS, requested_count * 2))


def _route_user_message(model: str, message: str, selected_recipe_id: Optional[int]) -> Dict[str, str]:
    prompt = "\n".join(
        [
            "判断用户问题是否需要查询本地菜谱库。",
            "只返回 JSON，不要输出其他文字。",
            "route 只能是 recipe 或 general。",
            "recipe: 用户在问菜谱、食材、调料、做法、烹饪建议、菜谱筛选或菜谱库数据。",
            "general: 普通闲聊、日期时间、常识、数学、翻译、和菜谱库无关的问题。",
            "{",
            '  "route": "recipe 或 general",',
            '  "reason": "一句话说明判断依据"',
            "}",
            "",
            "本轮不提供当前正在查看的菜谱上下文。",
            f"用户问题: {message}",
        ]
    )
    messages = [
        {
            "role": "system",
            "content": "你是问题路由器。必须输出合法 JSON。不要输出 markdown，不要输出代码块。",
        },
        {"role": "user", "content": prompt},
    ]
    try:
        raw_content = _call_ollama_chat_logged(
            feature="assistant_chat",
            stage="route",
            model=model,
            messages=messages,
            meta={"message": message, "selected_recipe_id": selected_recipe_id},
        )
        parsed = _extract_json_object(raw_content)
        route = str(parsed.get("route", "")).strip().lower()
        if route not in {"recipe", "general"}:
            route = _fallback_route(message, selected_recipe_id)
        return {
            "route": route,
            "reason": str(parsed.get("reason", "")).strip(),
            "raw": raw_content,
        }
    except Exception:
        return {
            "route": _fallback_route(message, selected_recipe_id),
            "reason": "路由阶段未得到稳定 JSON，使用关键词回退判断。",
            "raw": "",
        }


def _fallback_route(message: str, selected_recipe_id: Optional[int]) -> str:
    recipe_keywords = (
        "菜",
        "菜谱",
        "食材",
        "调料",
        "做法",
        "烹饪",
        "下饭",
        "不辣",
        "辣",
        "早餐",
        "午餐",
        "晚餐",
        "推荐",
        "筛选",
        "标签",
        "鸡肉",
        "牛肉",
        "猪肉",
        "羊肉",
        "鱼",
        "虾",
    )
    if selected_recipe_id and any(token in message for token in ("这个", "这道", "当前", "它")):
        return "recipe"
    return "recipe" if any(token in message for token in recipe_keywords) else "general"


def _interpret_for_retrieval(
    *,
    model_name: str,
    message: str,
    use_deepseek_interpretation: bool,
) -> Dict[str, Any]:
    if use_deepseek_interpretation:
        try:
            return _normalize_interpretation_payload(interpret_recipe_query_with_deepseek(message))
        except Exception as error:
            fallback = _interpret_user_message(model_name, message)
            fallback["source"] = "deepseek_fallback"
            fallback["notes"] = (
                f"{fallback.get('notes') or ''} DeepSeek需求解析失败，已回退本地解析：{error}"
            ).strip()
            return _normalize_interpretation_payload(fallback)
    return _normalize_interpretation_payload(_interpret_user_message(model_name, message))


def _normalize_interpretation_payload(interpretation: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(interpretation or {})
    for key in (
        "concepts",
        "expanded_terms",
        "constraints",
        "include_terms",
        "exclude_terms",
        "prefer_terms",
        "search_terms",
    ):
        normalized[key] = _normalize_text_list(normalized.get(key))
    return normalized


def _safe_requested_count(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 30 else None


def _maybe_rerank_context_items(
    *,
    message: str,
    interpretation: Dict[str, Any],
    context_items: List[Dict[str, Any]],
    requested_count: Optional[int],
    allow_external_rerank: bool,
) -> Dict[str, Any]:
    if not allow_external_rerank:
        return {"enabled": False, "source": "local_only", "ranked_ids": []}
    if not context_items:
        return {"enabled": True, "source": "deepseek", "ranked_ids": [], "notes": "No local candidates to rerank."}
    try:
        return rerank_recipe_candidates_with_deepseek(
            message=message,
            interpretation=interpretation,
            candidates=context_items,
            target_count=requested_count,
        )
    except Exception as error:
        return {
            "enabled": True,
            "source": "deepseek_error",
            "ranked_ids": [],
            "error": str(error),
            "notes": "External rerank failed; local ranking was kept.",
        }


def _apply_external_rerank(
    context_items: List[Dict[str, Any]],
    rerank: Dict[str, Any],
) -> List[Dict[str, Any]]:
    ranked_ids = [int(item_id) for item_id in rerank.get("ranked_ids", []) if str(item_id).isdigit()]
    if not ranked_ids:
        return context_items
    by_id = {int(item["id"]): item for item in context_items if item.get("id") is not None}
    ordered: List[Dict[str, Any]] = []
    seen = set()
    explanations = rerank.get("explanations") or {}
    for recipe_id in ranked_ids:
        item = by_id.get(recipe_id)
        if not item:
            continue
        item = dict(item)
        item["source"] = "deepseek_rerank"
        explanation = explanations.get(str(recipe_id))
        if explanation:
            item["reasons"] = [explanation] + [reason for reason in item.get("reasons", []) if reason != explanation]
        ordered.append(item)
        seen.add(recipe_id)
    ordered.extend(item for item in context_items if int(item.get("id") or -1) not in seen)
    return ordered


def _build_general_messages(message: str) -> List[Dict[str, str]]:
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    return [
        {
            "role": "system",
            "content": (
                "你是本地菜谱应用里的普通助手。"
                "当前用户问题不需要查询菜谱库时，直接回答用户当前问题。"
                "只输出最终给用户看的回答，不要输出思考过程、分析步骤、草稿或英文内部标记。"
                "不要说“当前库内上下文不足”，不要延续上一轮菜谱筛选条件。"
                f"当前本地时间: {current_time}。"
            ),
        },
        {"role": "user", "content": message},
    ]


def _answer_general_message(
    *,
    model_name: str,
    message: str,
    route: Dict[str, str],
    route_elapsed_ms: int,
) -> Dict[str, Any]:
    answer_started = time.perf_counter()
    messages = _build_general_messages(message)
    answer = _call_ollama_chat_logged(
        feature="assistant_chat",
        stage="general_answer",
        model=model_name,
        messages=messages,
        meta={"message": message, "route": route},
    )
    answer_elapsed_ms = int((time.perf_counter() - answer_started) * 1000)
    return {
        "message": message,
        "model": model_name,
        "selected_recipe_id": None,
        "answer": answer,
        "citations": [],
        "interpretation": {
            "intent": "普通问答",
            "concepts": [],
            "expanded_terms": [],
            "constraints": [],
            "retrieval_query": "",
            "notes": route.get("reason") or "本轮问题不需要查询菜谱库。",
            "raw": route.get("raw") or "",
            "source": "route_general",
        },
        "retrieval": {"query": "", "understanding": {}, "items": [], "total": 0},
        "pipeline": {
            "mode": "general_chat",
            "route_ms": route_elapsed_ms,
            "interpretation_ms": 0,
            "retrieval_ms": 0,
            "answer_ms": answer_elapsed_ms,
        },
    }


def _stream_general_message(
    *,
    model_name: str,
    message: str,
    route: Dict[str, str],
    route_elapsed_ms: int,
    show_reasoning: bool,
) -> Generator[str, None, None]:
    messages = _build_general_messages(message)
    answer_parts: List[str] = []
    thinking_parts: List[str] = []
    answer_started = time.perf_counter()
    yield _encode_stream_event({"type": "stage", "stage": "general_answer"})
    try:
        for chunk in _stream_ollama_chat(model_name, messages, include_thinking=show_reasoning):
            if chunk["type"] == "answer_chunk":
                answer_parts.append(chunk["delta"])
            elif chunk["type"] == "thinking_chunk":
                thinking_parts.append(chunk["delta"])
            yield _encode_stream_event(chunk)
    except Exception as error:
        create_ai_conversation_log(
            feature="assistant_chat",
            stage="general_answer",
            model=model_name,
            request_messages=messages,
            status="error",
            error_text=str(error),
            meta={"message": message, "route": route, "stream": True},
        )
        raise

    answer = "".join(answer_parts).strip()
    if not answer:
        raise RuntimeError("Ollama returned an empty response")
    answer_elapsed_ms = int((time.perf_counter() - answer_started) * 1000)
    interpretation = {
        "intent": "普通问答",
        "concepts": [],
        "expanded_terms": [],
        "constraints": [],
        "retrieval_query": "",
        "notes": route.get("reason") or "本轮问题不需要查询菜谱库。",
        "raw": route.get("raw") or "",
        "source": "route_general",
    }
    if show_reasoning and thinking_parts:
        interpretation["raw_thinking"] = "".join(thinking_parts).strip()

    create_ai_conversation_log(
        feature="assistant_chat",
        stage="general_answer",
        model=model_name,
        request_messages=messages,
        status="success",
        response_text=answer,
        meta={
            "message": message,
            "route": route,
            "stream": True,
            "thinking": "".join(thinking_parts).strip() if thinking_parts else "",
        },
    )
    yield _encode_stream_event(
        {
            "type": "final",
            "result": {
                "message": message,
                "model": model_name,
                "selected_recipe_id": None,
                "answer": answer,
                "citations": [],
                "interpretation": interpretation,
                "retrieval": {"query": "", "understanding": {}, "items": [], "total": 0},
                "pipeline": {
                    "mode": "general_chat",
                    "route_ms": route_elapsed_ms,
                    "interpretation_ms": 0,
                    "retrieval_ms": 0,
                    "answer_ms": answer_elapsed_ms,
                },
            },
        }
    )


def _interpret_user_message(model: str, message: str) -> Dict[str, Any]:
    vocabulary_text = format_library_vocabulary_summary(get_library_vocabulary_summary())
    prompt = "\n".join(
        [
            "请把用户问题解释成适合菜谱检索的中间结果。",
            "你会看到一份库内低风险词表摘要。它只包含标签、专题库、分组、菜系和高频可见食材，不包含具体菜谱正文。",
            "优先使用词表中存在的准确词来构建检索短句、展开词和限制条件。",
            "如果用户的模糊需求能对应到已有自动标签，请把相关标签写入 expanded_terms 或 retrieval_query。",
            "你必须只返回 JSON，不要输出其他文字。",
            "JSON 结构如下：",
            "{",
            '  "intent": "问题意图简述",',
            '  "concepts": ["从问题中抽出的模糊概念"],',
            '  "expanded_terms": ["为了检索可展开的词"],',
            '  "constraints": ["明显的限制条件"],',
            '  "retrieval_query": "用于后续检索的短句",',
            '  "notes": "如果有歧义，用一句话说明"',
            "}",
            "",
            f"用户问题：{message}",
            "",
            vocabulary_text,
        ]
    )

    messages = [
        {
            "role": "system",
            "content": "你是菜谱检索解释器。输出必须是合法 JSON。不要输出 markdown，不要输出代码块。",
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]

    try:
        raw_content = _call_ollama_chat_logged(
            feature="assistant_chat",
            stage="interpretation",
            model=model,
            messages=messages,
            meta={"message": message},
        )
        parsed = _extract_json_object(raw_content)
        return {
            "intent": str(parsed.get("intent", "")).strip(),
            "concepts": _normalize_string_list(parsed.get("concepts")),
            "expanded_terms": _normalize_string_list(parsed.get("expanded_terms")),
            "constraints": _normalize_string_list(parsed.get("constraints")),
            "retrieval_query": str(parsed.get("retrieval_query", "")).strip() or message,
            "notes": str(parsed.get("notes", "")).strip(),
            "raw": raw_content,
            "source": "llm",
        }
    except Exception:
        return {
            "intent": "直接按原问题检索",
            "concepts": [],
            "expanded_terms": [],
            "constraints": [],
            "retrieval_query": message,
            "notes": "概念解释阶段未得到稳定 JSON，已回退到原问题直接检索。",
            "raw": "",
            "source": "fallback",
        }


def _call_ollama_chat(
    model: str,
    messages: List[Dict[str, str]],
    *,
    response_format: Optional[Any] = None,
    extra_options: Optional[Dict[str, Any]] = None,
) -> str:
    payload = _build_ollama_payload(
        model,
        messages,
        stream=False,
        include_thinking=False,
        response_format=response_format,
        extra_options=extra_options,
    )

    with httpx.Client(timeout=OLLAMA_TIMEOUT_SECONDS, trust_env=False) as client:
        response = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()

    content = _strip_model_thinking((body.get("message") or {}).get("content", ""))
    if not content:
        raise RuntimeError("Ollama returned an empty response")
    return content


def _stream_ollama_chat(
    model: str,
    messages: List[Dict[str, str]],
    *,
    include_thinking: bool,
) -> Generator[Dict[str, str], None, None]:
    payload = _build_ollama_payload(model, messages, stream=True, include_thinking=include_thinking)
    content_parts: List[str] = []

    with httpx.Client(timeout=OLLAMA_TIMEOUT_SECONDS, trust_env=False) as client:
        with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                message = chunk.get("message") or {}
                thinking_delta = (message.get("thinking") or "").strip()
                if include_thinking and thinking_delta:
                    yield {"type": "thinking_chunk", "delta": thinking_delta}
                content_delta = (message.get("content") or "").strip()
                if content_delta:
                    if include_thinking:
                        yield {"type": "answer_chunk", "delta": content_delta}
                    else:
                        content_parts.append(content_delta)
                if chunk.get("done"):
                    if chunk.get("error"):
                        raise RuntimeError(str(chunk.get("error")))
                    break

    if not include_thinking:
        content = _strip_model_thinking("".join(content_parts))
        if content:
            yield {"type": "answer_chunk", "delta": content}


def _build_ollama_payload(
    model: str,
    messages: List[Dict[str, str]],
    *,
    stream: bool,
    include_thinking: bool,
    response_format: Optional[Any] = None,
    extra_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options: Dict[str, Any] = {"temperature": 0.2}
    if extra_options:
        options.update(extra_options)
    payload: Dict[str, Any] = {
        "model": model,
        "stream": stream,
        "messages": messages,
        "options": options,
    }
    if not include_thinking:
        payload["think"] = False
    if response_format is not None:
        payload["format"] = response_format
    return payload


def _strip_model_thinking(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    if not re.search(r"Thinking\s*Process|ThinkingProcess|Final\s*(Answer|Version|Response|Plan)|Drafting|Refining", text, re.I):
        return text

    marker_patterns = (
        r"最终回答[:：]",
        r"最终答案[:：]",
        r"答案[:：]",
        r"Final\s*Answer\s*[:：]",
        r"Final\s*Version\s*[:：]",
        r"Final\s*Response\s*[:：]",
        r"Response\s*[:：]",
    )
    for pattern in marker_patterns:
        matches = list(re.finditer(pattern, text, flags=re.I))
        if matches:
            candidate = text[matches[-1].end() :].strip()
            candidate = _clean_thinking_tail(candidate)
            if candidate:
                return candidate

    chinese_candidates = re.findall(
        r"[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9，。！？、；：“”‘’（）《》\s]{12,}?[。！？]",
        text,
    )
    natural_candidates = [
        candidate.strip()
        for candidate in chinese_candidates
        if _looks_like_final_answer(candidate)
    ]
    if natural_candidates:
        return _clean_thinking_tail(natural_candidates[-1])

    return _clean_thinking_tail(text)


def _looks_like_final_answer(candidate: str) -> bool:
    if any(token in candidate for token in ("用户问题", "当前本地时间", "当前库内上下文不足", "不要延续", "不要说")):
        return False
    non_space_chars = [char for char in candidate if not char.isspace()]
    if not non_space_chars:
        return False
    chinese_count = sum(1 for char in non_space_chars if "\u4e00" <= char <= "\u9fff")
    return chinese_count / len(non_space_chars) >= 0.45


def _clean_thinking_tail(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^(?:\*+|[-\s])+", "", cleaned).strip()
    stop_markers = (
        "Wait,",
        "Okay,",
        "FinalPlan:",
        "FinalVersion:",
        "FinalResponse:",
        "FinalAnswer:",
        "ThinkingProcess:",
        "Thinking Process:",
    )
    marker_positions = [
        cleaned.find(marker)
        for marker in stop_markers
        if cleaned.find(marker) > 0
    ]
    if marker_positions:
        cleaned = cleaned[: min(marker_positions)].strip()
    return cleaned


def _encode_stream_event(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _build_chat_messages(
    user_message: str,
    selected_recipe: Optional[Dict[str, Any]],
    context_items: List[Dict[str, Any]],
    history: List[Dict[str, str]],
    interpretation: Dict[str, Any],
    requested_count: Optional[int] = None,
) -> List[Dict[str, str]]:
    system_prompt = _build_answer_system_prompt(user_message, interpretation)

    context_prompt = _build_context_prompt(
        user_message=user_message,
        selected_recipe=selected_recipe,
        context_items=context_items,
        interpretation=interpretation,
        requested_count=requested_count,
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": context_prompt})
    return messages


def _build_answer_system_prompt(user_message: str, interpretation: Dict[str, Any]) -> str:
    rules = [
        "你是本地菜谱助手。",
        "只能依据当前提供的菜谱上下文回答，不要编造库中不存在的菜。",
        "如果上下文里有可保守推荐的候选，不要因为缺少显式标签而直接拒答。",
        "只有完全没有可用候选或候选明显不符合时，才说明“当前库内上下文不足以确定”。",
        "回答时尽量直接，优先给出结论和理由。",
        "如果引用菜谱，请在菜名后标注对应的菜谱ID，例如：番茄炒蛋（ID 12）。",
        "不要输出思维链。",
    ]

    if _request_mentions_not_spicy(user_message, interpretation):
        rules.append(
            "本轮用户明确要求不辣时，优先排除明确出现辣椒、干辣椒、小米辣、辣酱、辣油、卡宴、cayenne、冬阴功、哈里萨等辣味线索的菜；"
            "剩余菜谱可按调料和做法保守判断，并说明“未见明显辣味调料”。"
        )
    if _request_mentions_rice_pairing(user_message, interpretation):
        rules.append("本轮用户明确要求下饭或配主食时，可以优先选择饭类、炖菜、煲类、酱汁较多或适合配主食的菜。")
    if _request_mentions_health_sensitive(user_message, interpretation):
        rules.append("本轮用户涉及健康、病号、术后、恢复、减脂等敏感场景时，不要给医学诊断，只按菜谱内容做保守建议。")

    if not any(
        (
            _request_mentions_not_spicy(user_message, interpretation),
            _request_mentions_rice_pairing(user_message, interpretation),
            _request_mentions_health_sensitive(user_message, interpretation),
        )
    ):
        rules.append("不要主动引入用户没有提出的限制条件，例如不辣、下饭、病号、减脂等；不要解释无关属性。")

    return "".join(rules)


def _request_text_for_condition(user_message: str, interpretation: Dict[str, Any]) -> str:
    interpretation = _normalize_interpretation_payload(interpretation)
    parts: List[str] = [user_message or ""]
    for key in (
        "intent",
        "retrieval_query",
        "notes",
    ):
        parts.append(str(interpretation.get(key) or ""))
    for key in (
        "concepts",
        "expanded_terms",
        "constraints",
        "include_terms",
        "exclude_terms",
        "prefer_terms",
        "search_terms",
    ):
        parts.extend(_normalize_text_list(interpretation.get(key)))
    return " ".join(part for part in parts if part)


def _request_mentions_not_spicy(user_message: str, interpretation: Dict[str, Any]) -> bool:
    text = _request_text_for_condition(user_message, interpretation).lower()
    return any(term in text for term in ("不辣", "不要辣", "不能辣", "别辣", "少辣", "免辣", "无辣"))


def _request_mentions_rice_pairing(user_message: str, interpretation: Dict[str, Any]) -> bool:
    text = _request_text_for_condition(user_message, interpretation)
    return any(term in text for term in ("下饭", "配饭", "配米饭", "拌饭", "盖饭", "主食"))


def _request_mentions_health_sensitive(user_message: str, interpretation: Dict[str, Any]) -> bool:
    text = _request_text_for_condition(user_message, interpretation)
    return any(term in text for term in ("病号", "病人", "恢复", "术后", "孕妇", "老人", "小孩", "减脂", "低脂", "低盐", "控糖"))


def _build_retrieval_query(user_message: str, interpretation: Dict[str, Any]) -> str:
    parts = [
        interpretation.get("retrieval_query") or "",
        user_message,
        " ".join(_normalize_text_list(interpretation.get("constraints"))),
        " ".join(_normalize_text_list(interpretation.get("include_terms"))),
        " ".join(_normalize_text_list(interpretation.get("exclude_terms"))),
        " ".join(_normalize_text_list(interpretation.get("prefer_terms"))),
        " ".join(_normalize_text_list(interpretation.get("search_terms"))),
    ]
    return " ".join(part.strip() for part in parts if str(part or "").strip())


def _normalize_text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    seen = set()
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
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _build_context_prompt(
    user_message: str,
    selected_recipe: Optional[Dict[str, Any]],
    context_items: List[Dict[str, Any]],
    interpretation: Dict[str, Any],
    requested_count: Optional[int] = None,
) -> str:
    interpretation = _normalize_interpretation_payload(interpretation)
    normalized_context_items: List[Dict[str, Any]] = []
    for item in context_items:
        normalized_item = dict(item)
        normalized_item["tags"] = _normalize_text_list(normalized_item.get("tags"))
        normalized_item["managed_tags"] = _normalize_text_list(normalized_item.get("managed_tags"))
        normalized_item["reasons"] = _normalize_text_list(normalized_item.get("reasons"))
        normalized_context_items.append(normalized_item)
    context_items = normalized_context_items

    lines: List[str] = [
        "任务：回答用户关于本地菜谱库的问题。",
        "",
        f"用户问题：{user_message}",
        "",
        "概念解释：",
        f"- 意图: {interpretation.get('intent') or ''}",
        f"- 模糊概念: {'；'.join(interpretation.get('concepts') or [])}",
        f"- 展开词: {'；'.join(interpretation.get('expanded_terms') or [])}",
        f"- 限制条件: {'；'.join(interpretation.get('constraints') or [])}",
        f"- 检索短句: {interpretation.get('retrieval_query') or ''}",
        f"- 备注: {interpretation.get('notes') or ''}",
    ]
    if requested_count:
        lines.append(f"- 用户期望数量: {requested_count}")
    lines.append("")

    if selected_recipe:
        lines.extend(
            [
                "当前用户正在查看的菜谱：",
                f"- ID: {selected_recipe['id']}",
                f"- 菜名: {selected_recipe['name']}",
                f"- 专题库: {selected_recipe.get('library_section') or ''}",
                f"- 分组: {selected_recipe.get('section_name') or ''}",
                f"- 菜系: {selected_recipe.get('cuisine') or selected_recipe.get('sub_cuisine') or ''}",
                "",
            ]
        )

    lines.append("可用菜谱上下文：")
    if not context_items:
        lines.append("- 没有检索到相关菜谱。")
    else:
        for item in context_items:
            lines.extend(
                [
                    f"- 菜谱ID: {item['id']}",
                    f"  菜名: {item['name']}",
                    f"  来源: {item['source']}",
                    f"  专题库: {item.get('library_section') or ''}",
                    f"  分组: {item.get('section_name') or ''}",
                    f"  菜系: {item.get('cuisine') or item.get('sub_cuisine') or ''}",
                    f"  原始标签: {', '.join(item.get('tags', [])) or '-'}",
                    f"  自动标签: {', '.join(item.get('managed_tags', [])) or '-'}",
                    f"  食材摘要: {item.get('ingredients_summary', '')}",
                    f"  调料摘要: {item.get('seasonings_summary', '')}",
                    f"  做法摘要: {item.get('steps_summary', '')}",
                ]
            )
            if item.get("reasons"):
                lines.append(f"  检索命中原因: {'；'.join(item['reasons'])}")
            lines.append("")

    output_rules = [
        "输出要求：",
        "1. 只依据上面的上下文回答。",
        f"2. 如果推荐菜谱，最多列出 {requested_count or '合适数量的'} 道，并简述理由。",
    ]
    if any(
        (
            _request_mentions_not_spicy(user_message, interpretation),
            _request_mentions_rice_pairing(user_message, interpretation),
            _request_mentions_health_sensitive(user_message, interpretation),
        )
    ):
        output_rules.append("3. 对用户本轮明确提出、但没有显式标签的条件，基于菜名、食材、调料、做法做保守判断；不要要求必须有明确标签。")
    else:
        output_rules.append("3. 不要主动判断或解释用户没有提出的属性，例如辣不辣、是否下饭、是否适合病号、是否减脂。")
    output_rules.extend(
        [
            "4. 如果候选数量少于用户要求，可以先列出可保守推荐的候选，再说明剩余数量无法确认。",
            "5. 如果引用了某道菜，请在菜名后标注对应的菜谱ID。",
        ]
    )
    lines.extend(output_rules)
    return "\n".join(lines)


def _normalize_history(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for item in history:
        role = (item.get("role") or "").strip()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _build_context_items(search_items: List[Dict[str, Any]], selected_recipe: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    context_items: List[Dict[str, Any]] = []
    seen_ids = set()

    if selected_recipe:
        context_items.append(_recipe_to_context_item(selected_recipe, source="selected"))
        seen_ids.add(selected_recipe["id"])

    for item in search_items:
        recipe_id = item["id"]
        if recipe_id in seen_ids:
            continue
        recipe_detail = get_recipe(recipe_id)
        if recipe_detail is None:
            continue
        context_items.append(
            _recipe_to_context_item(
                recipe_detail,
                source="search",
                score=item.get("score"),
                reasons=item.get("reasons", []),
            )
        )
        seen_ids.add(recipe_id)

    return context_items


def _recipe_to_context_item(
    recipe: Dict[str, Any],
    source: str,
    score: Optional[float] = None,
    reasons: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": recipe["id"],
        "name": recipe["name"],
        "source": source,
        "score": score,
        "reasons": reasons or [],
        "record_kind": recipe.get("record_kind"),
        "backlog_status": recipe.get("backlog_status"),
        "library_section": recipe.get("library_section"),
        "section_name": recipe.get("section_name"),
        "cuisine": recipe.get("cuisine"),
        "sub_cuisine": recipe.get("sub_cuisine"),
        "tags": recipe.get("tags", []),
        "managed_tags": recipe.get("managed_tags", []),
        "ingredients_summary": _summarize_context_text(recipe.get("ingredients_text"), MAX_CONTEXT_TEXT_CHARS),
        "seasonings_summary": _summarize_context_text(recipe.get("seasonings_text"), MAX_CONTEXT_TEXT_CHARS),
        "steps_summary": _summarize_steps_text(recipe.get("steps_text"), recipe.get("notes_text")),
    }


def _summarize_context_text(value: Optional[str], max_chars: int) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text:
        return "-"
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip(" ，,；;。") + "..."


def _summarize_steps_text(steps_text: Optional[str], notes_text: Optional[str]) -> str:
    steps = re.sub(r"\s+", " ", (steps_text or "").strip())
    notes = re.sub(r"\s+", " ", (notes_text or "").strip())
    combined = steps
    if notes:
        combined = f"{combined} 备注：{notes}" if combined else f"备注：{notes}"
    return _summarize_context_text(combined, MAX_CONTEXT_STEPS_CHARS)


def _build_citations(context_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "library_section": item.get("library_section"),
            "section_name": item.get("section_name"),
            "source": item.get("source"),
            "score": item.get("score"),
        }
        for item in context_items
    ]


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.replace("json", "", 1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    last_object: Optional[Dict[str, Any]] = None

    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            last_object = parsed

    if last_object is not None:
        return last_object

    raise ValueError("JSON object not found")


def _normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result
