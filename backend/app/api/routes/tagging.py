from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.managed_tag_service import (
    create_managed_tag,
    delete_managed_tag,
    get_tagging_status,
    list_managed_tags,
    list_managed_tag_recipes,
    pause_tagging_run,
    remove_managed_tag_assignment,
    resume_tagging_run,
    start_tagging_run,
    update_managed_tag,
)


router = APIRouter()


class ManagedTagPayload(BaseModel):
    name: str
    description: str = ""
    is_active: bool = True
    sort_order: int = 0


class StartTaggingPayload(BaseModel):
    model: Optional[str] = None


@router.get("/tagging/tags")
def tagging_tags():
    return list_managed_tags()


@router.post("/tagging/tags")
def tagging_create_tag(payload: ManagedTagPayload):
    try:
        return create_managed_tag(
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put("/tagging/tags/{tag_id}")
def tagging_update_tag(tag_id: int, payload: ManagedTagPayload):
    try:
        return update_managed_tag(
            tag_id=tag_id,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/tagging/tags/{tag_id}")
def tagging_delete_tag(tag_id: int):
    deleted = delete_managed_tag(tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Managed tag not found")
    return {"deleted": True}


@router.get("/tagging/tags/{tag_id}/recipes")
def tagging_tag_recipes(tag_id: int, search: str = "", limit: int = 100):
    try:
        return list_managed_tag_recipes(tag_id=tag_id, search=search, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/tagging/tags/{tag_id}/recipes/{recipe_id}")
def tagging_delete_tag_recipe(tag_id: int, recipe_id: int):
    try:
        return remove_managed_tag_assignment(tag_id=tag_id, recipe_id=recipe_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/tagging/status")
def tagging_status():
    return get_tagging_status()


@router.post("/tagging/run/start")
def tagging_run_start(payload: StartTaggingPayload):
    try:
        return start_tagging_run(model=payload.model)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/tagging/run/pause")
def tagging_run_pause():
    return pause_tagging_run()


@router.post("/tagging/run/resume")
def tagging_run_resume():
    try:
        return resume_tagging_run()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
