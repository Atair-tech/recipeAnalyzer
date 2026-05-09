import json
from typing import Dict, Optional

from pydantic import BaseModel

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.import_service import (
    get_import_batch_detail,
    list_import_batches,
    persist_import,
    preview_import,
)
from app.services.import_refine_service import (
    get_refine_status,
    pause_refine_run,
    resume_refine_run,
    start_refine_run,
)
from app.services.ingredient_visibility_service import (
    get_ingredient_filter_status,
    pause_ingredient_filter_run,
    resume_ingredient_filter_run,
    start_ingredient_filter_run,
)
from app.services.refine_review_service import (
    get_refine_review_detail,
    list_refine_review_items,
    rerun_refine_recipe,
    update_refine_review,
)


router = APIRouter()


class ImportRefineStartPayload(BaseModel):
    model: Optional[str] = None
    provider: Optional[str] = None


class RefineReviewUpdatePayload(BaseModel):
    status: str
    issue_type: Optional[str] = None
    note: Optional[str] = None


class RefineReviewRerunPayload(BaseModel):
    model: Optional[str] = None


@router.post("/imports/preview")
def import_preview(
    file: UploadFile = File(...),
    mapping_json: Optional[str] = Form(default=None),
):
    try:
        return preview_import(
            file.filename or "uploaded.xlsx",
            file.file,
            _parse_mapping_json(mapping_json),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to preview import: {error}") from error


@router.post("/imports/commit")
def import_commit(
    file: UploadFile = File(...),
    mapping_json: Optional[str] = Form(default=None),
):
    try:
        return persist_import(
            file.filename or "uploaded.xlsx",
            file.file,
            _parse_mapping_json(mapping_json),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to persist import: {error}") from error


@router.get("/imports/batches")
def import_batches(limit: int = 20):
    return list_import_batches(limit=limit)


@router.get("/imports/batches/{batch_id}")
def import_batch_detail(batch_id: int, row_limit: int = 20):
    batch = get_import_batch_detail(batch_id=batch_id, row_limit=row_limit)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return batch


@router.get("/imports/refine/status")
def import_refine_status():
    return get_refine_status()


@router.post("/imports/refine/start")
def import_refine_start(payload: ImportRefineStartPayload):
    try:
        return start_refine_run(payload.model)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/imports/refine/pause")
def import_refine_pause():
    return pause_refine_run()


@router.post("/imports/refine/resume")
def import_refine_resume():
    try:
        return resume_refine_run()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/imports/ingredient-filter/status")
def ingredient_filter_status():
    return get_ingredient_filter_status()


@router.post("/imports/ingredient-filter/start")
def ingredient_filter_start(payload: ImportRefineStartPayload):
    try:
        return start_ingredient_filter_run(payload.model, provider=payload.provider)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/imports/ingredient-filter/pause")
def ingredient_filter_pause():
    return pause_ingredient_filter_run()


@router.post("/imports/ingredient-filter/resume")
def ingredient_filter_resume():
    try:
        return resume_ingredient_filter_run()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/imports/refine/review")
def import_refine_review_list(
    search: Optional[str] = None,
    status: str = "all",
    issue_type: Optional[str] = None,
    limit: int = 200,
):
    return list_refine_review_items(search=search, status=status, issue_type=issue_type, limit=limit)


@router.get("/imports/refine/review/{recipe_id}")
def import_refine_review_detail(recipe_id: int):
    detail = get_refine_review_detail(recipe_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return detail


@router.put("/imports/refine/review/{recipe_id}")
def import_refine_review_update(recipe_id: int, payload: RefineReviewUpdatePayload):
    try:
        return update_refine_review(
            recipe_id=recipe_id,
            status=payload.status,
            note=payload.note,
            issue_type=payload.issue_type,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/imports/refine/review/{recipe_id}/rerun")
def import_refine_review_rerun(recipe_id: int, payload: RefineReviewRerunPayload):
    try:
        return rerun_refine_recipe(recipe_id=recipe_id, model=payload.model)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to rerun refine: {error}") from error


def _parse_mapping_json(mapping_json: Optional[str]) -> Optional[Dict[str, str]]:
    if not mapping_json:
        return None

    try:
        parsed = json.loads(mapping_json)
    except json.JSONDecodeError as error:
        raise ValueError("Invalid mapping payload") from error

    if not isinstance(parsed, dict):
        raise ValueError("Invalid mapping payload")

    return parsed
