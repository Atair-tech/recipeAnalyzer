import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from app.services.ai_log_service import create_ai_conversation_log
from app.services.recipe_service import get_recipe
from app.services.search_service import natural_search


OLLAMA_BASE_URL = os.getenv("RECIPE_ANALYZER_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = os.getenv("RECIPE_ANALYZER_OLLAMA_MODEL", "qwen3:0.6b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("RECIPE_ANALYZER_OLLAMA_TIMEOUT", "240"))


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
        return {
            "available": True,
            "base_url": OLLAMA_BASE_URL,
            "default_model": OLLAMA_DEFAULT_MODEL,
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


def ask_recipe_assistant(
    message: str,
    model: Optional[str] = None,
    selected_recipe_id: Optional[int] = None,
    top_k: int = 6,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    normalized_message = (message or "").strip()
    if not normalized_message:
        raise ValueError("Message is required")

    model_name = (model or OLLAMA_DEFAULT_MODEL).strip()
    safe_top_k = max(1, min(int(top_k), 12))
    normalized_history = _normalize_history(history or [])
    selected_recipe = get_recipe(selected_recipe_id) if selected_recipe_id else None

    interpretation_started = time.perf_counter()
    interpretation = _interpret_user_message(model_name, normalized_message)
    interpretation_elapsed_ms = int((time.perf_counter() - interpretation_started) * 1000)

    retrieval_query = interpretation.get("retrieval_query") or normalized_message
    retrieval_extra_terms = interpretation.get("expanded_terms") or []

    retrieval_started = time.perf_counter()
    search_result = natural_search(
        retrieval_query,
        limit=safe_top_k,
        offset=0,
        extra_terms=retrieval_extra_terms,
    )
    context_items = _build_context_items(search_result.get("items", []), selected_recipe)
    citations = _build_citations(context_items)
    retrieval_elapsed_ms = int((time.perf_counter() - retrieval_started) * 1000)

    answer_started = time.perf_counter()
    messages = _build_chat_messages(
        user_message=normalized_message,
        selected_recipe=selected_recipe,
        context_items=context_items,
        history=normalized_history,
        interpretation=interpretation,
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
        },
        "pipeline": {
            "interpretation_ms": interpretation_elapsed_ms,
            "retrieval_ms": retrieval_elapsed_ms,
            "answer_ms": answer_elapsed_ms,
        },
    }


def _interpret_user_message(model: str, message: str) -> Dict[str, Any]:
    prompt = "\n".join(
        [
            "请把用户问题解释成适合菜谱检索的中间结果。",
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


def _call_ollama_chat(model: str, messages: List[Dict[str, str]]) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {
            "temperature": 0.2,
        },
    }

    with httpx.Client(timeout=OLLAMA_TIMEOUT_SECONDS, trust_env=False) as client:
        response = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()
        body = response.json()

    content = (body.get("message") or {}).get("content", "").strip()
    if not content:
        raise RuntimeError("Ollama returned an empty response")
    return content


def _build_chat_messages(
    user_message: str,
    selected_recipe: Optional[Dict[str, Any]],
    context_items: List[Dict[str, Any]],
    history: List[Dict[str, str]],
    interpretation: Dict[str, Any],
) -> List[Dict[str, str]]:
    system_prompt = (
        "你是本地菜谱助手。"
        "只能依据当前提供的菜谱上下文回答，不要编造库中不存在的菜。"
        "如果上下文不足，就明确说明“当前库内上下文不足以确定”。"
        "回答时尽量直接，优先给出结论和理由。"
        "如果引用菜谱，请在菜名后标注对应的菜谱ID，例如：番茄炒蛋（ID 12）。"
        "不要输出思维链。"
    )

    context_prompt = _build_context_prompt(
        user_message=user_message,
        selected_recipe=selected_recipe,
        context_items=context_items,
        interpretation=interpretation,
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": context_prompt})
    return messages


def _build_context_prompt(
    user_message: str,
    selected_recipe: Optional[Dict[str, Any]],
    context_items: List[Dict[str, Any]],
    interpretation: Dict[str, Any],
) -> str:
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
        "",
    ]

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
                    f"  标签: {', '.join(item.get('tags', []))}",
                    f"  食材: {item.get('ingredients_text', '')}",
                    f"  调料: {item.get('seasonings_text', '')}",
                    f"  做法及要点: {item.get('steps_text', '')}",
                    f"  备注: {item.get('notes_text', '')}",
                    f"  来源备注: {item.get('source_reference', '')}",
                ]
            )
            if item.get("reasons"):
                lines.append(f"  检索命中原因: {'；'.join(item['reasons'])}")
            lines.append("")

    lines.extend(
        [
            "输出要求：",
            "1. 只依据上面的上下文回答。",
            "2. 如果推荐菜谱，优先列出菜名，并简述理由。",
            "3. 如果信息不足，直接说明“当前库内上下文不足以确定”。",
            "4. 如果引用了某道菜，请在菜名后标注对应的菜谱ID。",
            "5. 如果用户问题涉及健康、病号、术后、减脂等敏感场景，不要给医学诊断，只按菜谱内容做保守建议。",
        ]
    )
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
        "ingredients_text": recipe.get("ingredients_text") or "",
        "seasonings_text": recipe.get("seasonings_text") or "",
        "steps_text": recipe.get("steps_text") or "",
        "notes_text": recipe.get("notes_text") or "",
        "source_reference": recipe.get("source_reference") or "",
    }


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
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.replace("json", "", 1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON object not found")

    return json.loads(cleaned[start : end + 1])


def _normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result
