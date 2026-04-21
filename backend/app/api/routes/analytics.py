from fastapi import APIRouter, Query

from app.services.analytics_service import get_analytics_summary


router = APIRouter()


@router.get("/analytics/summary")
def analytics_summary(
    dimension: str = Query(default="library_section"),
    scope: str = Query(default="all"),
    top_n: int = Query(default=12),
):
    return get_analytics_summary(dimension=dimension, scope=scope, top_n=top_n)
