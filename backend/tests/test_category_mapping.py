import json
from pathlib import Path

import pytest

from app.services.ai import category_mapping
from app.services.ai.category_mapping import (
    CategoryMappingError,
    MAPPED_WASTE_CATEGORIES,
    classify_waste_object,
    get_category_metadata,
    load_category_mapping,
)


EXPECTED_CLASSES = {
    "battery",
    "cardboard_carton",
    "cigarette",
    "contaminated_packaging",
    "dirty_tissue",
    "disposable_plastic_container",
    "disposable_utensils_straw",
    "drink_can",
    "electronic_waste",
    "foam_styrofoam",
    "food_wrapper",
    "food_waste",
    "general_waste",
    "glass",
    "other_plastic",
    "paper",
    "plastic_bag_film",
    "plastic_bottle",
    "large_appliance",
    "large_table",
    "mattress",
    "refrigerator",
    "rope_strings",
    "scrap_metal",
    "small_accessory",
    "sofa",
    "used_diaper",
    "washing_machine",
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
        assert metadata["waste_category"] in MAPPED_WASTE_CATEGORIES


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
        "waste_category": "Unknown",
        "material": "Unknown",
        "recyclable": False,
        "recommended_handling": (
            "Keep separate and request manual classification before disposal."
        ),
    }


@pytest.mark.parametrize(
    ("name", "expected_name", "expected_category"),
    [
        ("plastic_bottle", "plastic_bottle", "Recyclable Waste"),
        ("plastic_container", "disposable_plastic_container", "Recyclable Waste"),
        ("drink_can", "drink_can", "Recyclable Waste"),
        ("metal_can", "drink_can", "Recyclable Waste"),
        ("paper", "paper", "Recyclable Waste"),
        ("cardboard_box", "cardboard_carton", "Recyclable Waste"),
        ("glass_bottle", "glass", "Recyclable Waste"),
        ("food_wrapper", "food_wrapper", "Non-Recyclable"),
        ("dirty_tissue", "dirty_tissue", "Non-Recyclable"),
        ("used_diaper", "used_diaper", "Non-Recyclable"),
        ("styrofoam", "foam_styrofoam", "Non-Recyclable"),
        ("contaminated_packaging", "contaminated_packaging", "Non-Recyclable"),
        ("sofa", "sofa", "Bulky Waste"),
        ("mattress", "mattress", "Bulky Waste"),
        ("large_table", "large_table", "Bulky Waste"),
        ("refrigerator", "refrigerator", "Bulky Waste"),
        ("washing_machine", "washing_machine", "Bulky Waste"),
        ("large_appliance", "large_appliance", "Bulky Waste"),
    ],
)
def test_backend_mapping_classifies_required_objects(
    name: str,
    expected_name: str,
    expected_category: str,
) -> None:
    result = classify_waste_object(name, "Unknown")

    assert result["name"] == expected_name
    assert result["category"] == expected_category
    assert result["category_source"] == "mapping"


def test_backend_mapping_wins_over_vlm_suggestion() -> None:
    assert classify_waste_object("plastic bottle", "Bulky Waste") == {
        "name": "plastic_bottle",
        "display_name": "Plastic Bottle",
        "category": "Recyclable Waste",
        "category_source": "mapping",
    }


@pytest.mark.parametrize(
    "suggestion",
    ["Non-Recyclable", "Recyclable Waste", "Bulky Waste"],
)
def test_unmapped_object_can_use_valid_vlm_suggestion(suggestion: str) -> None:
    assert classify_waste_object("ceramic plant pot", suggestion) == {
        "name": "ceramic_plant_pot",
        "display_name": "Ceramic Plant Pot",
        "category": suggestion,
        "category_source": "vlm",
    }


@pytest.mark.parametrize(
    "suggestion",
    [None, "", "Unknown", "Other", "Recyclable"],
)
def test_unmapped_object_remains_unknown_for_unclear_or_invalid_vlm_category(
    suggestion: str | None,
) -> None:
    assert classify_waste_object("ceramic plant pot", suggestion) == {
        "name": "ceramic_plant_pot",
        "display_name": "Ceramic Plant Pot",
        "category": "Unknown",
        "category_source": "unknown",
    }


def test_mapping_rejects_unsupported_category(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mapping_path = tmp_path / "unsupported-category.json"
    mapping_path.write_text(
        json.dumps(
            {
                "plastic_bottle": {
                    "display_name": "Plastic Bottle",
                    "waste_category": "Other",
                    "material": "Plastic",
                    "recyclable": True,
                    "recommended_handling": "Use an appropriate collection stream.",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(category_mapping, "MAPPING_PATH", mapping_path)
    load_category_mapping.cache_clear()

    try:
        with pytest.raises(CategoryMappingError, match="unsupported waste_category"):
            load_category_mapping()
    finally:
        load_category_mapping.cache_clear()


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
