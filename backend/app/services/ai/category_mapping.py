"""Deterministic metadata mapping for YOLO waste classes."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


MAPPING_PATH = (
    Path(__file__).resolve().parents[4] / "ai" / "config" / "waste_categories.json"
)


class WasteCategoryMetadata(TypedDict):
    display_name: str
    waste_category: str
    material: str
    recyclable: bool
    recommended_handling: str


class CategoryMappingError(RuntimeError):
    """Raised when the category mapping cannot be loaded or validated."""


def normalize_class_name(class_name: str) -> str:
    """Normalize common YOLO class-name formats to mapping keys."""

    return class_name.strip().lower().replace("-", "_").replace(" ", "_")


def _validate_metadata(class_name: str, value: object) -> WasteCategoryMetadata:
    if not isinstance(value, dict):
        raise CategoryMappingError(
            f"Mapping for '{class_name}' must be a JSON object."
        )

    string_fields = (
        "display_name",
        "waste_category",
        "material",
        "recommended_handling",
    )
    for field in string_fields:
        field_value = value.get(field)
        if not isinstance(field_value, str) or not field_value.strip():
            raise CategoryMappingError(
                f"Mapping for '{class_name}' requires a non-empty '{field}'."
            )

    recyclable = value.get("recyclable")
    if not isinstance(recyclable, bool):
        raise CategoryMappingError(
            f"Mapping for '{class_name}' requires a boolean 'recyclable'."
        )

    return {
        "display_name": value["display_name"],
        "waste_category": value["waste_category"],
        "material": value["material"],
        "recyclable": recyclable,
        "recommended_handling": value["recommended_handling"],
    }


@lru_cache(maxsize=1)
def load_category_mapping() -> dict[str, WasteCategoryMetadata]:
    """Load and validate the editable JSON mapping once per process."""

    if not MAPPING_PATH.is_file():
        raise CategoryMappingError(f"Category mapping not found: {MAPPING_PATH}")

    try:
        raw_mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CategoryMappingError(f"Failed to load category mapping: {exc}") from exc

    if not isinstance(raw_mapping, dict):
        raise CategoryMappingError("Category mapping must be a JSON object.")

    mapping: dict[str, WasteCategoryMetadata] = {}
    for raw_class_name, raw_metadata in raw_mapping.items():
        if not isinstance(raw_class_name, str) or not raw_class_name.strip():
            raise CategoryMappingError("Category mapping keys must be non-empty strings.")
        normalized_name = normalize_class_name(raw_class_name)
        mapping[normalized_name] = _validate_metadata(normalized_name, raw_metadata)

    return mapping


def reload_category_mapping() -> dict[str, WasteCategoryMetadata]:
    """Clear the cache and reload mapping changes from disk."""

    load_category_mapping.cache_clear()
    return load_category_mapping()


def get_category_metadata(class_name: str) -> WasteCategoryMetadata:
    """Return deterministic metadata, with a safe fallback for unknown classes."""

    normalized_name = normalize_class_name(class_name)
    metadata = load_category_mapping().get(normalized_name)
    if metadata is not None:
        return metadata.copy()

    return {
        "display_name": normalized_name.replace("_", " ").title(),
        "waste_category": "Uncategorized Waste",
        "material": "Unknown",
        "recyclable": False,
        "recommended_handling": (
            "Keep separate and request manual classification before disposal."
        ),
    }
