from copy import deepcopy
from typing import Any

import pytest

from app.services.ai.grouping_service import (
    GroupingInputError,
    group_fused_objects,
    load_group_labels,
)
from app.services.ai.object_normalization import load_object_name_mapping


def fused_object(
    name: str,
    *,
    display_name: str,
    category: str,
    source: str,
    confidence: float | None,
    box: dict[str, float] | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": display_name,
        "category": category,
        "category_source": "mapping",
        "source": source,
        "confidence": confidence,
        "confidence_level": None if confidence is not None else "high",
        "supported_by_vlm": source == "yolo+vlm",
        "bounding_box": box,
    }


def bottle(confidence: float, x1: float, source: str = "yolo") -> dict[str, Any]:
    return fused_object(
        "plastic_bottle",
        display_name="Plastic Bottle",
        category="Recyclable Waste",
        source=source,
        confidence=confidence,
        box={"x1": x1, "y1": 2.0, "x2": x1 + 10.0, "y2": 20.0},
    )


def test_single_yolo_object_uses_singular_label() -> None:
    result = group_fused_objects([bottle(0.91, 1.0)])

    assert result == {
        "grouped_objects": [
            {
                "name": "plastic_bottle",
                "label": "Plastic Bottle",
                "count": 1,
                "category": "Recyclable Waste",
                "sources": ["yolo"],
                "average_yolo_confidence": 0.91,
            }
        ]
    }


def test_repeated_yolo_objects_use_explicit_multiple_label_and_average() -> None:
    result = group_fused_objects(
        [
            bottle(0.95, 1.0, "yolo+vlm"),
            bottle(0.90, 20.0, "yolo+vlm"),
            bottle(0.85, 40.0, "yolo+vlm"),
        ]
    )

    assert result == {
        "grouped_objects": [
            {
                "name": "plastic_bottle",
                "label": "Pile of Plastic Bottles",
                "count": 3,
                "category": "Recyclable Waste",
                "sources": ["yolo", "vlm"],
                "average_yolo_confidence": 0.9,
            }
        ]
    }


def test_drink_cans_use_explicit_multiple_label() -> None:
    objects = [
        fused_object(
            "drink_can",
            display_name="Drink Can",
            category="Recyclable Waste",
            source="yolo",
            confidence=0.8,
            box={"x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0},
        ),
        fused_object(
            "drink_can",
            display_name="Drink Can",
            category="Recyclable Waste",
            source="yolo",
            confidence=0.9,
            box={"x1": 5.0, "y1": 6.0, "x2": 7.0, "y2": 8.0},
        ),
    ]

    assert group_fused_objects(objects)["grouped_objects"][0]["label"] == (
        "Pile of Drink Cans"
    )


def test_single_mattress_uses_singular_label() -> None:
    item = fused_object(
        "mattress",
        display_name="Mattress",
        category="Bulky Waste",
        source="yolo",
        confidence=0.88,
        box={"x1": 1.0, "y1": 2.0, "x2": 30.0, "y2": 40.0},
    )

    grouped = group_fused_objects([item])["grouped_objects"][0]

    assert grouped["label"] == "Mattress"
    assert grouped["count"] == 1


def test_vlm_only_observation_has_no_invented_exact_count() -> None:
    item = fused_object(
        "mattress",
        display_name="Mattress",
        category="Bulky Waste",
        source="vlm",
        confidence=None,
        box=None,
    )

    grouped = group_fused_objects([item])["grouped_objects"][0]

    assert grouped == {
        "name": "mattress",
        "label": "Mattress",
        "count": None,
        "category": "Bulky Waste",
        "sources": ["vlm"],
        "average_yolo_confidence": None,
    }


def test_grouping_does_not_modify_individual_objects_or_bounding_boxes() -> None:
    objects = [bottle(0.91, 1.0), bottle(0.82, 20.0)]
    original = deepcopy(objects)

    group_fused_objects(objects)

    assert objects == original
    assert objects[0]["bounding_box"] != objects[1]["bounding_box"]


def test_all_controlled_objects_have_explicit_labels() -> None:
    assert set(load_object_name_mapping()) == set(load_group_labels())


def test_conflicting_categories_are_rejected() -> None:
    first = bottle(0.91, 1.0)
    second = {**bottle(0.82, 20.0), "category": "Unknown"}

    with pytest.raises(GroupingInputError, match="conflicting final categories"):
        group_fused_objects([first, second])
