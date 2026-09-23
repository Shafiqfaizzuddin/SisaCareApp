from app.services.ai.category_mapping import (
    get_category_metadata,
    load_category_mapping,
)


EXPECTED_CLASSES = {
    "plastic_bottle",
    "plastic_bag",
    "metal_can",
    "cardboard",
    "paper",
    "glass",
    "food_waste",
    "general_waste",
    "construction_debris",
    "electronic_waste",
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
