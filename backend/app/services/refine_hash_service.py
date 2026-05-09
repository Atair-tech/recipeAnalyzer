import hashlib
import json
from typing import Any, Dict


REFINEMENT_SOURCE_FIELDS = (
    "name",
    "library_section",
    "section_name",
    "ingredients_text",
    "seasonings_text",
)


def build_refinement_source_hash(payload: Dict[str, Any]) -> str:
    serialized = json.dumps(
        {
            "version": "ingredient-refine-input-v1",
            "fields": {
                field: _normalize_refinement_value(payload.get(field))
                for field in REFINEMENT_SOURCE_FIELDS
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def refinement_inputs_equal(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return all(
        _normalize_refinement_value(left.get(field)) == _normalize_refinement_value(right.get(field))
        for field in REFINEMENT_SOURCE_FIELDS
    )


def _normalize_refinement_value(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
