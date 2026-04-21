from fastapi import APIRouter

from app.services.recipe_service import get_overview


router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "recipe-analyzer-api", "upload_support": True}


@router.get("/overview")
def overview():
    return get_overview()
