import json
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from app.services.ai_log_service import create_ai_conversation_log
from app.services.library_context_service import format_library_vocabulary_summary, get_library_vocabulary_summary


DEEPSEEK_BASE_URL = os.getenv("RECIPE_ANALYZER_DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_DEFAULT_MODEL = os.getenv("RECIPE_ANALYZER_DEEPSEEK_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv("RECIPE_ANALYZER_DEEPSEEK_TIMEOUT", "300"))
DEEPSEEK_REASONING_EFFORT = os.getenv("RECIPE_ANALYZER_DEEPSEEK_REASONING_EFFORT", "high").strip()


def is_deepseek_configured() -> bool:
    return bool(_get_deepseek_api_key())


def interpret_recipe_query_with_deepseek(message: str) -> Dict[str, Any]:
    """Send only the user question to DeepSeek and return retrieval-friendly JSON."""
    api_key = _get_deepseek_api_key()
    if not api_key:
        raise ValueError("DeepSeek API key is not configured")

    user_message = (message or "").strip()
    vocabulary_summary = get_library_vocabulary_summary()
    vocabulary_text = format_library_vocabulary_summary(vocabulary_summary)
    prompt = "\n".join(
        [
            "Return JSON only.",
            "Task: convert a Chinese recipe-search request into retrieval constraints.",
            "Privacy rule: the input contains only the user's question plus a low-risk vocabulary summary. No dish records, full recipes, cooking steps, notes, or workbook rows are provided.",
            "Do not invent dish names. Expand implicit cooking concepts into searchable terms.",
            "Prefer terms that exist in the vocabulary summary when they are relevant.",
            "If a user concept maps to existing automatic tags, put those tag names into prefer_terms or search_terms.",
            "If a user asks for a topic/group/cuisine/ingredient that exists in the vocabulary summary, use the exact vocabulary term.",
            "Use include_terms for hard requirements. Use exclude_terms for hard negative terms.",
            "Use prefer_terms for soft preferences and semantic clues.",
            "For '不辣', include spicy ingredients and cuisine clues in exclude_terms, for example: 辣, 辣椒, 干辣椒, 小米辣, 辣酱, 辣油, 卡宴, cayenne, 冬阴功, 哈里萨, harissa.",
            "For '病号/恢复/清淡', prefer mild, soft, digestible, soup, porridge, steamed, less oil, and avoid heavy spicy/oily/fried terms.",
            "If the user asks for a number of dishes, set target_count.",
            "",
            "Required JSON format:",
            json.dumps(
                {
                    "intent": "short intent",
                    "target_count": 3,
                    "include_terms": ["牛肉", "饭"],
                    "exclude_terms": ["辣椒"],
                    "prefer_terms": ["清淡", "软烂", "下饭"],
                    "search_terms": ["牛肉饭", "盖饭"],
                    "retrieval_query": "compact search query",
                    "notes": "one short note",
                },
                ensure_ascii=False,
            ),
            "",
            f"User question: {user_message}",
            "",
            vocabulary_text,
        ]
    )
    messages = [
        {"role": "system", "content": "You are a JSON-only recipe query parser. No markdown."},
        {"role": "user", "content": prompt},
    ]
    content = _call_deepseek_json(messages=messages, max_tokens=4096, feature="assistant_chat", stage="deepseek_interpret")
    parsed = _extract_json_payload(content)
    include_terms = _string_list(parsed.get("include_terms"))
    exclude_terms = _string_list(parsed.get("exclude_terms"))
    prefer_terms = _string_list(parsed.get("prefer_terms"))
    search_terms = _string_list(parsed.get("search_terms"))
    target_count = _safe_int(parsed.get("target_count"))
    return {
        "intent": str(parsed.get("intent") or "").strip(),
        "concepts": _dedupe(include_terms + prefer_terms),
        "expanded_terms": _dedupe(search_terms + prefer_terms),
        "constraints": _dedupe(include_terms + [f"排除:{term}" for term in exclude_terms]),
        "include_terms": include_terms,
        "exclude_terms": exclude_terms,
        "prefer_terms": prefer_terms,
        "search_terms": search_terms,
        "target_count": target_count,
        "retrieval_query": str(parsed.get("retrieval_query") or "").strip() or user_message,
        "notes": str(parsed.get("notes") or "").strip(),
        "raw": content,
        "source": "deepseek",
    }


def rerank_recipe_candidates_with_deepseek(
    *,
    message: str,
    interpretation: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    target_count: Optional[int],
) -> Dict[str, Any]:
    """Optionally send sanitized candidate summaries to DeepSeek for ranking only."""
    api_key = _get_deepseek_api_key()
    if not api_key:
        raise ValueError("DeepSeek API key is not configured")

    limited_candidates = candidates[:20]
    candidate_payload = [_sanitize_candidate(item) for item in limited_candidates]
    prompt = "\n".join(
        [
            "Return JSON only.",
            "Task: rerank local recipe candidates for the user request.",
            "Privacy rule: candidates are sanitized summaries. Do not ask for or infer hidden recipe details.",
            "Choose only from provided ids. Do not create new dishes.",
            "If evidence is weak, still rank the best candidates and explain uncertainty briefly.",
            "",
            "Required JSON format:",
            json.dumps(
                {
                    "ranked_ids": [1, 2, 3],
                    "explanations": {"1": "short reason"},
                    "notes": "short note",
                },
                ensure_ascii=False,
            ),
            "",
            f"User question: {(message or '').strip()}",
            f"Parsed request: {json.dumps(_sanitize_interpretation(interpretation), ensure_ascii=False)}",
            f"Target count: {target_count or ''}",
            "Candidates:",
            json.dumps(candidate_payload, ensure_ascii=False),
        ]
    )
    messages = [
        {"role": "system", "content": "You are a JSON-only recipe candidate reranker. No markdown."},
        {"role": "user", "content": prompt},
    ]
    content = _call_deepseek_json(messages=messages, max_tokens=8192, feature="assistant_chat", stage="deepseek_rerank")
    parsed = _extract_json_payload(content)
    valid_ids = {int(item["id"]) for item in limited_candidates if item.get("id") is not None}
    ranked_ids = []
    for item in parsed.get("ranked_ids") or []:
        item_id = _safe_int(item)
        if item_id in valid_ids and item_id not in ranked_ids:
            ranked_ids.append(item_id)
    explanations = parsed.get("explanations") if isinstance(parsed.get("explanations"), dict) else {}
    return {
        "source": "deepseek",
        "enabled": True,
        "ranked_ids": ranked_ids,
        "explanations": {str(key): str(value) for key, value in explanations.items()},
        "notes": str(parsed.get("notes") or "").strip(),
        "raw": content,
    }


def _call_deepseek_json(
    *,
    messages: List[Dict[str, str]],
    max_tokens: int,
    feature: str,
    stage: str,
) -> str:
    payload: Dict[str, Any] = {
        "model": DEEPSEEK_DEFAULT_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "stream": False,
    }
    if DEEPSEEK_REASONING_EFFORT:
        payload["reasoning_effort"] = DEEPSEEK_REASONING_EFFORT

    try:
        with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS, trust_env=False) as client:
            response = client.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {_get_deepseek_api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        content = (((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise ValueError("DeepSeek returned empty content")
        create_ai_conversation_log(
            feature=feature,
            stage=stage,
            model=DEEPSEEK_DEFAULT_MODEL,
            request_messages=messages,
            status="success",
            response_text=content,
            meta={"provider": "deepseek"},
        )
        return content
    except Exception as error:
        create_ai_conversation_log(
            feature=feature,
            stage=stage,
            model=DEEPSEEK_DEFAULT_MODEL,
            request_messages=messages,
            status="error",
            error_text=str(error),
            meta={"provider": "deepseek"},
        )
        raise


def _sanitize_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "section": item.get("library_section"),
        "group": item.get("section_name"),
        "cuisine": item.get("cuisine") or item.get("sub_cuisine"),
        "auto_tags": item.get("managed_tags") or [],
        "ingredients": _clip(item.get("ingredients_summary"), 80),
        "seasonings": _clip(item.get("seasonings_summary"), 60),
        "match_reasons": item.get("reasons") or [],
        "local_score": item.get("score"),
    }


def _sanitize_interpretation(interpretation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "intent": interpretation.get("intent"),
        "include_terms": interpretation.get("include_terms") or [],
        "exclude_terms": interpretation.get("exclude_terms") or [],
        "prefer_terms": interpretation.get("prefer_terms") or [],
        "search_terms": interpretation.get("search_terms") or [],
        "target_count": interpretation.get("target_count"),
    }


def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
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
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("JSON object not found")


def _get_deepseek_api_key() -> str:
    return (os.getenv("RECIPE_ANALYZER_DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip()


def _string_list(value: Any) -> List[str]:
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
    return _dedupe(normalized)


def _safe_int(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 30 else None


def _dedupe(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _clip(value: Any, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip(" ,，、。；;") + "..."
