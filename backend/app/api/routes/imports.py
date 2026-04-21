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


router = APIRouter()


class ImportRefineStartPayload(BaseModel):
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
