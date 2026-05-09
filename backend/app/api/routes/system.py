import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.env import save_local_env_value
from app.services.birthday_surprise_service import (
    acknowledge_birthday_surprise_event,
    get_pending_birthday_surprise_event,
)
from app.services.recipe_service import get_overview


router = APIRouter()


class DeepSeekApiKeyPayload(BaseModel):
    api_key: str


class BirthdaySurpriseAckPayload(BaseModel):
    event_id: str


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "recipe-analyzer-api", "upload_support": True}


@router.get("/overview")
def overview():
    return get_overview()


@router.get("/birthday-surprise/event")
def birthday_surprise_event():
    return get_pending_birthday_surprise_event()


@router.post("/birthday-surprise/event/ack")
def birthday_surprise_event_ack(payload: BirthdaySurpriseAckPayload):
    return acknowledge_birthday_surprise_event(payload.event_id)


@router.get("/settings/deepseek-api-key")
def deepseek_api_key_status():
    return {"configured": _has_deepseek_api_key(), "source": _deepseek_api_key_source()}


@router.post("/settings/deepseek-api-key")
def save_deepseek_api_key(payload: DeepSeekApiKeyPayload):
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    if len(api_key) < 8:
        raise HTTPException(status_code=400, detail="API key is too short")

    save_local_env_value("RECIPE_ANALYZER_DEEPSEEK_API_KEY", api_key)
    return {"configured": True}


def _has_deepseek_api_key() -> bool:
    return bool((os.getenv("RECIPE_ANALYZER_DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or "").strip())


def _deepseek_api_key_source() -> Optional[str]:
    if (os.getenv("RECIPE_ANALYZER_DEEPSEEK_API_KEY") or "").strip():
        return "RECIPE_ANALYZER_DEEPSEEK_API_KEY"
    if (os.getenv("DEEPSEEK_API_KEY") or "").strip():
        return "DEEPSEEK_API_KEY"
    return None
