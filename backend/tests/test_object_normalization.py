import json
from pathlib import Path

import pytest

from app.services.ai import object_normalization
from app.services.ai.category_mapping import load_category_mapping
from app.services.ai.object_normalization import (
    ObjectNameMappingError,
    get_object_display_name,
    load_object_name_mapping,
    normalize_label_format,
    normalize_object,
    normalize_object_name,
)


@pytest.mark.parametrize(
    "label",
    ["Plastic Bottle", "plastic bottle", "plastic_bottle"],
)
def test_plastic_bottle_variants_share_one_canonical_name(label: str) -> None:
    assert normalize_object_name(label) == "plastic_bottle"


@pytest.mark.parametrize(
    "label",
    [
        "Drink Can",
        "drink can",
        "metal drink can",
        "beverage can",
        "metal_can",
    ],
)
def test_controlled_drink_can_aliases_share_one_canonical_name(label: str) -> None:
    assert normalize_object_name(label) == "drink_can"
    assert get_object_display_name(label) == "Drink Can"


def test_separator_normalization_is_deterministic() -> None:
    assert normalize_label_format("  Rope & Strings  ") == "rope_strings"
    assert normalize_label_format("Food-wrapper") == "food_wrapper"
    assert normalize_label_format("cardboard / carton") == "cardboard_carton"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("plastic bottles", "plastic_bottles"),
        ("plastic bottel", "plastic_bottel"),
        ("bottle plastic", "bottle_plastic"),
        ("metal food can", "metal_food_can"),
        ("tin can", "tin_can"),
    ],
)
def test_unknown_or_related_labels_are_not_aggressively_merged(
    label: str,
    expected: str,
) -> None:
    assert normalize_object_name(label) == expected


def test_normalized_object_includes_canonical_display_and_known_status() -> None:
    assert normalize_object("discarded fridge") == {
        "canonical_name": "refrigerator",
        "display_name": "Refrigerator",
        "known": True,
    }
    assert normalize_object("ceramic plant pot") == {
        "canonical_name": "ceramic_plant_pot",
        "display_name": "Ceramic Plant Pot",
        "known": False,
    }


def test_all_current_yolo_category_keys_have_object_name_definitions() -> None:
    definitions = load_object_name_mapping()
    assert set(load_category_mapping()).issubset(definitions)


def test_mapping_returns_caller_safe_copies() -> None:
    first = load_object_name_mapping()
    first["plastic_bottle"]["display_name"] = "Changed"
    first["plastic_bottle"]["aliases"].append("changed alias")

    second = load_object_name_mapping()
    assert second["plastic_bottle"]["display_name"] == "Plastic Bottle"
    assert "changed alias" not in second["plastic_bottle"]["aliases"]


def _use_mapping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mapping: object,
) -> None:
    mapping_path = tmp_path / "object-names.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setattr(object_normalization, "MAPPING_PATH", mapping_path)
    object_normalization._load_registry.cache_clear()


def test_mapping_is_easy_to_extend_without_code_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_mapping(
        monkeypatch,
        tmp_path,
        {
            "ceramic_mug": {
                "display_name": "Ceramic Mug",
                "aliases": ["coffee mug", "ceramic cup"],
            }
        },
    )
    try:
        assert normalize_object_name("coffee mug") == "ceramic_mug"
        assert get_object_display_name("ceramic cup") == "Ceramic Mug"
    finally:
        object_normalization._load_registry.cache_clear()


def test_conflicting_aliases_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_mapping(
        monkeypatch,
        tmp_path,
        {
            "drink_can": {
                "display_name": "Drink Can",
                "aliases": ["metal can"],
            },
            "food_can": {
                "display_name": "Food Can",
                "aliases": ["metal can"],
            },
        },
    )
    try:
        with pytest.raises(ObjectNameMappingError, match="conflicts"):
            load_object_name_mapping()
    finally:
        object_normalization._load_registry.cache_clear()


def test_invalid_canonical_name_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _use_mapping(
        monkeypatch,
        tmp_path,
        {
            "Plastic Bottle": {
                "display_name": "Plastic Bottle",
                "aliases": [],
            }
        },
    )
    try:
        with pytest.raises(ObjectNameMappingError, match="lowercase snake_case"):
            load_object_name_mapping()
    finally:
        object_normalization._load_registry.cache_clear()


@pytest.mark.parametrize("label", ["", "  ", "---"])
def test_empty_normalized_label_is_rejected(label: str) -> None:
    with pytest.raises(ValueError, match="letters or numbers"):
        normalize_object_name(label)


def test_non_string_label_is_rejected() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        normalize_object_name(123)  # type: ignore[arg-type]
