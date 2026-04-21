from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.ai_log_service import get_ai_conversation_log, list_ai_conversation_logs
from app.services.excel_export_service import build_excel_bytes, normalize_filename
from app.services.ollama_service import ask_recipe_assistant, get_ollama_status, list_ollama_models
from app.services.search_service import get_natural_search_export_rows, natural_search
from app.services.tag_suggestion_service import suggest_tags_for_recipe


router = APIRouter()


class LlmChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    selected_recipe_id: Optional[int] = None
    top_k: int = 6
    history: list[dict[str, str]] = []


@router.get("/ai/natural-search")
def ai_natural_search(
    q: str = Query(default=""),
    limit: int = Query(default=10),
    offset: int = Query(default=0),
):
    return natural_search(q, limit=limit, offset=offset)


@router.get("/ai/natural-search/export")
def ai_natural_search_export(q: str = Query(default="")):
    rows = get_natural_search_export_rows(q)
    headers = list(rows[0].keys()) if rows else ["菜名", "记录类型", "专题库", "分组", "菜系", "亚菜系", "标签", "食材", "BMD", "CC", "得分", "命中原因"]
    excel_bytes = build_excel_bytes(
        sheet_name="自然语言搜索",
        headers=headers,
        rows=[[row.get(header, "") for header in headers] for row in rows],
    )
    file_name = normalize_filename(f"natural_search_{q or 'results'}", "natural_search_results")
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/ai/recipes/{recipe_id}/tag-suggestions")
def ai_tag_suggestions(recipe_id: int, limit: int = Query(default=8)):
    result = suggest_tags_for_recipe(recipe_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return result


@router.get("/ai/llm/status")
def ai_llm_status():
    return get_ollama_status()


@router.get("/ai/llm/models")
def ai_llm_models():
    try:
        return {
            "items": list_ollama_models(),
        }
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail=f"Ollama request failed: {error}") from error


@router.post("/ai/llm/chat")
def ai_llm_chat(payload: LlmChatRequest):
    try:
        return ask_recipe_assistant(
            message=payload.message,
            model=payload.model,
            selected_recipe_id=payload.selected_recipe_id,
            top_k=payload.top_k,
            history=payload.history,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail=f"Ollama request failed: {error}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/ai/logs")
def ai_logs(
    limit: int = Query(default=50),
    offset: int = Query(default=0),
    feature: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    return list_ai_conversation_logs(
        limit=limit,
        offset=offset,
        feature=feature,
        status=status,
    )


@router.get("/ai/logs/{log_id}")
def ai_log_detail(log_id: int):
    item = get_ai_conversation_log(log_id)
    if item is None:
        raise HTTPException(status_code=404, detail="AI log not found")
    return item
