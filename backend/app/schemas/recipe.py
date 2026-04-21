from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class RecipeUpdatePayload(BaseModel):
    name: str = Field(min_length=1)
    alias: Optional[str] = None
    category: Optional[str] = None
    cuisine: Optional[str] = None
    flavor: Optional[str] = None
    difficulty: Optional[str] = None
    estimated_time: Optional[int] = None
    servings: Optional[int] = None
    tools: Optional[str] = None
    ingredients_text: Optional[str] = None
    steps_text: Optional[str] = None
    notes_text: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator(
        "name",
        "alias",
        "category",
        "cuisine",
        "flavor",
        "difficulty",
        "tools",
        "ingredients_text",
        "steps_text",
        "notes_text",
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

    @field_validator("estimated_time", "servings", mode="before")
    @classmethod
    def normalize_numeric_values(cls, value):
        if value in (None, ""):
            return None
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
