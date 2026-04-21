from typing import Optional

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, HTTPException, Response, status

from app.services.pairing_service import (
    create_pair_override,
    create_pair_overrides_bulk,
    delete_pair_override,
    get_pairing_review,
)


router = APIRouter()


class PairOverridePayload(BaseModel):
    library_section: str = Field(min_length=1)
    index_ref: Optional[str] = None
    index_name: str = Field(min_length=1)
    detail_ref: Optional[str] = None
    detail_name: str = Field(min_length=1)

    @field_validator("library_section", "index_name", "detail_name", "index_ref", "detail_ref")
    @classmethod
    def strip_values(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PairOverrideBulkPayload(BaseModel):
    items: list[PairOverridePayload] = Field(default_factory=list)


@router.get("/pairing/review")
def pairing_review():
    try:
        return get_pairing_review()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to load pairing review: {error}") from error


@router.post("/pairing/overrides", status_code=status.HTTP_201_CREATED)
def pairing_override_create(payload: PairOverridePayload):
    try:
        item = create_pair_override(
            library_section=payload.library_section,
            index_ref=payload.index_ref,
            index_name=payload.index_name,
            detail_ref=payload.detail_ref,
            detail_name=payload.detail_name,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to create pairing override: {error}") from error

    return {"item": item}


@router.post("/pairing/overrides/bulk", status_code=status.HTTP_201_CREATED)
def pairing_override_bulk_create(payload: PairOverrideBulkPayload):
    try:
        items = create_pair_overrides_bulk([item.model_dump() for item in payload.items])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to create pairing overrides: {error}") from error

    return {"items": items, "count": len(items)}


@router.delete("/pairing/overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def pairing_override_delete(override_id: int):
    deleted = delete_pair_override(override_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Pairing override not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
