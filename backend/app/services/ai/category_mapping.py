"""Backend-owned waste classification with an explicit VLM fallback."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, TypedDict, cast

from app.services.ai.object_normalization import (
    normalize_label_format,
    normalize_object,
    normalize_object_name,
)


MAPPING_PATH = (
    Path(__file__).resolve().parents[4] / "ai" / "config" / "waste_categories.json"
)

WasteCategory = Literal[
    "Non-Recyclable",
    "Recyclable Waste",
    "Bulky Waste",
    "Unknown",
]
CategorySource = Literal["mapping", "vlm", "unknown"]

MAPPED_WASTE_CATEGORIES = frozenset(
    {"Non-Recyclable", "Recyclable Waste", "Bulky Waste"}
)
VLM_WASTE_CATEGORIES = MAPPED_WASTE_CATEGORIES | {"Unknown"}


class WasteCategoryMetadata(TypedDict):
    display_name: str
    waste_category: str
    material: str
    recyclable: bool
    recommended_handling: str


class WasteClassification(TypedDict):
    name: str
    display_name: str
    category: WasteCategory
    category_source: CategorySource


class CategoryMappingError(RuntimeError):
    """Raised when the category mapping cannot be loaded or validated."""


def normalize_class_name(class_name: str) -> str:
    """Normalize common YOLO class-name formats to mapping keys."""

    return normalize_label_format(class_name)


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

    waste_category = value["waste_category"].strip()
    if waste_category not in MAPPED_WASTE_CATEGORIES:
        raise CategoryMappingError(
            f"Mapping for '{class_name}' has unsupported waste_category "
            f"'{waste_category}'."
        )

    return {
        "display_name": value["display_name"].strip(),
        "waste_category": waste_category,
        "material": value["material"].strip(),
        "recyclable": recyclable,
        "recommended_handling": value["recommended_handling"].strip(),
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
        if not normalized_name:
            raise CategoryMappingError(
                f"Mapping key '{raw_class_name}' has no usable class-name characters."
            )
        canonical_name = normalize_object_name(normalized_name)
        if canonical_name in mapping:
            raise CategoryMappingError(
                f"Duplicate normalized mapping key: '{canonical_name}'."
            )
        mapping[canonical_name] = _validate_metadata(canonical_name, raw_metadata)

    return mapping


def reload_category_mapping() -> dict[str, WasteCategoryMetadata]:
    """Clear the cache and reload mapping changes from disk."""

    load_category_mapping.cache_clear()
    return load_category_mapping()


def get_category_metadata(class_name: str) -> WasteCategoryMetadata:
    """Return deterministic metadata, with a safe fallback for unknown classes."""

    normalized_name = normalize_object_name(class_name)
    metadata = load_category_mapping().get(normalized_name)
    if metadata is not None:
        return metadata.copy()

    return {
        "display_name": normalize_object(class_name)["display_name"],
        "waste_category": "Unknown",
        "material": "Unknown",
        "recyclable": False,
        "recommended_handling": (
            "Keep separate and request manual classification before disposal."
        ),
    }


def classify_waste_object(
    name: str,
    vlm_suggested_category: str | None = None,
) -> WasteClassification:
    """Classify an object, preferring backend mapping over a valid VLM suggestion."""

    normalized = normalize_object(name)
    canonical_name = normalized["canonical_name"]
    metadata = load_category_mapping().get(canonical_name)
    if metadata is not None:
        return {
            "name": canonical_name,
            "display_name": metadata["display_name"],
            "category": cast(WasteCategory, metadata["waste_category"]),
            "category_source": "mapping",
        }

    if isinstance(vlm_suggested_category, str):
        suggested_category = vlm_suggested_category.strip()
        if suggested_category in MAPPED_WASTE_CATEGORIES:
            return {
                "name": canonical_name,
                "display_name": normalized["display_name"],
                "category": cast(WasteCategory, suggested_category),
                "category_source": "vlm",
            }

    return {
        "name": canonical_name,
        "display_name": normalized["display_name"],
        "category": "Unknown",
        "category_source": "unknown",
    }


__all__ = [
    "CategoryMappingError",
    "CategorySource",
    "MAPPED_WASTE_CATEGORIES",
    "VLM_WASTE_CATEGORIES",
    "WasteCategory",
    "WasteCategoryMetadata",
    "WasteClassification",
    "classify_waste_object",
    "get_category_metadata",
    "load_category_mapping",
    "normalize_class_name",
    "reload_category_mapping",
]
