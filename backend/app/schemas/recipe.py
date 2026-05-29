from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class RecipeUpdatePayload(BaseModel):
    name: str = Field(min_length=1)
    record_kind: Optional[str] = "recipe"
    backlog_status: Optional[str] = None
    library_section: Optional[str] = None
    section_name: Optional[str] = None
    category: Optional[str] = None
    cuisine: Optional[str] = None
    sub_cuisine: Optional[str] = None
    ingredients_text: Optional[str] = None
    seasonings_text: Optional[str] = None
    steps_text: Optional[str] = None
    notes_text: Optional[str] = None
    source_reference: Optional[str] = None
    last_reviewed_on: Optional[str] = None
    bmd_flag: bool = False
    cc_flag: bool = False
    source_text: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator(
        "name",
        "record_kind",
        "backlog_status",
        "library_section",
        "section_name",
        "category",
        "cuisine",
        "sub_cuisine",
        "ingredients_text",
        "seasonings_text",
        "steps_text",
        "notes_text",
        "source_reference",
        "last_reviewed_on",
        "source_text",
        mode="before",
    )
    @classmethod
    def strip_string_values(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]):
        if not value:
            raise ValueError("Recipe name is required")
        return value

    @field_validator("record_kind")
    @classmethod
    def validate_record_kind(cls, value: Optional[str]):
        if not value:
            return "recipe"
        if value not in {"recipe", "backlog"}:
            raise ValueError("record_kind must be recipe or backlog")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",")]
        return value

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: List[str]):
        cleaned: List[str] = []
        seen = set()

        for tag in value:
            normalized = tag.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                cleaned.append(normalized)

        return cleaned


class RecipeEditorRowPayload(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict)


class RecipeEditorCreatePayload(RecipeEditorRowPayload):
    pass


class TableEditorRowsPayload(BaseModel):
    table: str = Field(min_length=1)
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class UserViewRowsPayload(BaseModel):
    view: str = Field(min_length=1)
    filters: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_column: Optional[str] = None
    sort_direction: Optional[str] = None


class UserViewFilterValuesPayload(BaseModel):
    view: str = Field(min_length=1)
    column: str = Field(min_length=1)
    filters: Dict[str, Any] = Field(default_factory=dict)
    search: Optional[str] = None
    limit: int = Field(default=5000, ge=1, le=5000)


class TableEditorSqlPayload(BaseModel):
    sql: str = Field(min_length=1)


class TableEditorApplyPayload(BaseModel):
    table: str = Field(min_length=1)
    changes: List[Dict[str, Any]] = Field(default_factory=list)
