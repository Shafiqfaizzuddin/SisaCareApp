import json
from pathlib import Path

import pytest

from app.services.ai import category_mapping
from app.services.ai.category_mapping import (
    CategoryMappingError,
    get_category_metadata,
    load_category_mapping,
)


EXPECTED_CLASSES = {
    "battery",
    "cardboard_carton",
    "cigarette",
    "disposable_plastic_container",
    "disposable_utensils_straw",
    "electronic_waste",
    "foam_styrofoam",
    "food_waste",
    "general_waste",
    "glass",
    "other_plastic",
    "paper",
    "plastic_bag_film",
    "plastic_bottle",
    "rope_strings",
    "scrap_metal",
    "small_accessory",
}


def test_mapping_contains_expected_classes() -> None:
    mapping = load_category_mapping()

    assert set(mapping) == EXPECTED_CLASSES
    for metadata in mapping.values():
        assert set(metadata) == {
            "display_name",
            "waste_category",
            "material",
            "recyclable",
            "recommended_handling",
        }


def test_mapping_normalizes_class_names() -> None:
    assert get_category_metadata("Plastic Bottle") == get_category_metadata(
        "plastic-bottle"
    )
    assert get_category_metadata("Rope & strings") == get_category_metadata(
        "rope_strings"
    )


def test_mapping_returns_a_copy() -> None:
    metadata = get_category_metadata("plastic_bottle")
    metadata["display_name"] = "Changed"

    assert get_category_metadata("plastic_bottle")["display_name"] == "Plastic Bottle"


def test_unknown_class_uses_deterministic_fallback() -> None:
    assert get_category_metadata("unknown_item") == {
        "display_name": "Unknown Item",
        "waste_category": "Uncategorized Waste",
        "material": "Unknown",
        "recyclable": False,
        "recommended_handling": (
            "Keep separate and request manual classification before disposal."
        ),
    }


def test_mapping_rejects_duplicate_normalized_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    metadata = {
        "display_name": "Plastic Bottle",
        "waste_category": "Recyclable Waste",
        "material": "Plastic",
        "recyclable": True,
        "recommended_handling": "Use the plastic recycling stream.",
    }
    mapping_path = tmp_path / "duplicate-mapping.json"
    mapping_path.write_text(
        json.dumps(
            {
                "Plastic Bottle": metadata,
                "plastic-bottle": metadata,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(category_mapping, "MAPPING_PATH", mapping_path)
    load_category_mapping.cache_clear()

    try:
        with pytest.raises(CategoryMappingError, match="Duplicate normalized"):
            load_category_mapping()
    finally:
        load_category_mapping.cache_clear()
