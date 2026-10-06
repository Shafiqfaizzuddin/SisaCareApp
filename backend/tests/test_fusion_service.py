from typing import Any

import pytest

from app.services.ai.fusion_service import FusionInputError, fuse_waste_objects


def yolo_detection(
    name: str,
    confidence: float,
    box: tuple[float, float, float, float] = (1.0, 2.0, 30.0, 40.0),
) -> dict[str, Any]:
    return {
        "class_name": name,
        "class_id": 0,
        "confidence": confidence,
        "bounding_box": {
            "x1": box[0],
            "y1": box[1],
            "x2": box[2],
            "y2": box[3],
        },
        "source": "yolo",
    }


def vlm_observation(
    name: str,
    confidence_level: str = "high",
    suggested_category: str = "Unknown",
) -> dict[str, Any]:
    return {
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "suggested_category": suggested_category,
        "confidence_level": confidence_level,
        "reason": "The object is visibly present.",
    }


def test_matching_yolo_and_vlm_create_one_supported_record() -> None:
    box = {"x1": 1.0, "y1": 2.0, "x2": 30.0, "y2": 40.0}

    result = fuse_waste_objects(
        [yolo_detection("plastic_bottle", 0.91)],
        [vlm_observation("Plastic Bottle")],
    )

    assert result == [
        {
            "name": "plastic_bottle",
            "display_name": "Plastic Bottle",
            "category": "Recyclable Waste",
            "category_source": "mapping",
            "source": "yolo+vlm",
            "confidence": 0.91,
            "confidence_level": None,
            "supported_by_vlm": True,
            "bounding_box": box,
        }
    ]


def test_aliases_match_through_controlled_normalization() -> None:
    result = fuse_waste_objects(
        [yolo_detection("metal_can", 0.88)],
        [vlm_observation("drink can")],
    )

    assert len(result) == 1
    assert result[0]["name"] == "drink_can"
    assert result[0]["category"] == "Recyclable Waste"
    assert result[0]["category_source"] == "mapping"
    assert result[0]["source"] == "yolo+vlm"
    assert result[0]["supported_by_vlm"] is True


def test_multiple_yolo_instances_remain_separate_when_vlm_agrees() -> None:
    detections = [
        yolo_detection("plastic bottle", 0.93, (1, 2, 10, 20)),
        yolo_detection("plastic_bottle", 0.81, (30, 40, 50, 60)),
        yolo_detection("plastic-bottle", 0.42, (70, 80, 90, 100)),
    ]

    result = fuse_waste_objects(detections, [vlm_observation("plastic bottle")])

    assert len(result) == 3
    assert [item["confidence"] for item in result] == [0.93, 0.81, 0.42]
    assert [item["bounding_box"] for item in result] == [
        {"x1": 1.0, "y1": 2.0, "x2": 10.0, "y2": 20.0},
        {"x1": 30.0, "y1": 40.0, "x2": 50.0, "y2": 60.0},
        {"x1": 70.0, "y1": 80.0, "x2": 90.0, "y2": 100.0},
    ]
    assert all(item["source"] == "yolo+vlm" for item in result)
    assert all(item["category"] == "Recyclable Waste" for item in result)
    assert all(item["category_source"] == "mapping" for item in result)
    assert all(item["supported_by_vlm"] is True for item in result)


def test_low_confidence_yolo_is_supported_when_vlm_agrees() -> None:
    result = fuse_waste_objects(
        [yolo_detection("food_wrapper", 0.21)],
        [vlm_observation("food wrapper", "medium")],
    )

    assert result[0]["confidence"] == 0.21
    assert result[0]["confidence_level"] is None
    assert result[0]["supported_by_vlm"] is True
    assert result[0]["source"] == "yolo+vlm"
    assert result[0]["category"] == "Non-Recyclable"
    assert result[0]["category_source"] == "mapping"


def test_vlm_only_object_has_no_numeric_confidence_or_bounding_box() -> None:
    result = fuse_waste_objects([], [vlm_observation("mattress", "high")])

    assert result == [
        {
            "name": "mattress",
            "display_name": "Mattress",
            "category": "Bulky Waste",
            "category_source": "mapping",
            "source": "vlm",
            "confidence": None,
            "confidence_level": "high",
            "supported_by_vlm": False,
            "bounding_box": None,
        }
    ]


def test_disagreement_preserves_yolo_and_vlm_observations_separately() -> None:
    result = fuse_waste_objects(
        [yolo_detection("plastic_bottle", 0.97)],
        [vlm_observation("food wrapper", "low")],
    )

    assert [item["name"] for item in result] == ["plastic_bottle", "food_wrapper"]
    assert result[0]["source"] == "yolo"
    assert result[0]["category"] == "Recyclable Waste"
    assert result[0]["category_source"] == "mapping"
    assert result[0]["confidence"] == 0.97
    assert result[0]["supported_by_vlm"] is False
    assert result[0]["bounding_box"] is not None
    assert result[1]["source"] == "vlm"
    assert result[1]["category"] == "Non-Recyclable"
    assert result[1]["category_source"] == "mapping"
    assert result[1]["confidence_level"] == "low"
    assert result[1]["bounding_box"] is None


def test_duplicate_vlm_observations_collapse_to_strongest_confidence() -> None:
    result = fuse_waste_objects(
        [],
        [
            vlm_observation("discarded fridge", "low"),
            vlm_observation("refrigerator", "high"),
            vlm_observation("fridge", "medium"),
        ],
    )

    assert result == [
        {
            "name": "refrigerator",
            "display_name": "Refrigerator",
            "category": "Bulky Waste",
            "category_source": "mapping",
            "source": "vlm",
            "confidence": None,
            "confidence_level": "high",
            "supported_by_vlm": False,
            "bounding_box": None,
        }
    ]


def test_duplicate_vlm_observations_do_not_add_records_for_yolo_class() -> None:
    result = fuse_waste_objects(
        [yolo_detection("cardboard_carton", 0.75)],
        [
            vlm_observation("cardboard box", "medium"),
            vlm_observation("cardboard packaging", "high"),
        ],
    )

    assert len(result) == 1
    assert result[0]["source"] == "yolo+vlm"
    assert result[0]["category"] == "Recyclable Waste"
    assert result[0]["category_source"] == "mapping"
    assert result[0]["supported_by_vlm"] is True


def test_empty_inputs_return_empty_result() -> None:
    assert fuse_waste_objects([], []) == []


def test_vlm_suggestion_classifies_unmapped_object() -> None:
    result = fuse_waste_objects(
        [],
        [vlm_observation("ceramic plant pot", "medium", "Bulky Waste")],
    )

    assert result[0]["name"] == "ceramic_plant_pot"
    assert result[0]["display_name"] == "Ceramic Plant Pot"
    assert result[0]["category"] == "Bulky Waste"
    assert result[0]["category_source"] == "vlm"
    assert result[0]["source"] == "vlm"


def test_unmapped_object_with_unknown_vlm_suggestion_remains_unknown() -> None:
    result = fuse_waste_objects([], [vlm_observation("mystery debris")])

    assert result[0]["category"] == "Unknown"
    assert result[0]["category_source"] == "unknown"


def test_matching_vlm_classifies_unmapped_yolo_object() -> None:
    result = fuse_waste_objects(
        [yolo_detection("ceramic plant pot", 0.64)],
        [vlm_observation("ceramic_plant_pot", "medium", "Bulky Waste")],
    )

    assert result[0]["category"] == "Bulky Waste"
    assert result[0]["category_source"] == "vlm"
    assert result[0]["source"] == "yolo+vlm"
    assert result[0]["bounding_box"] is not None


def test_unmapped_yolo_only_object_remains_unknown() -> None:
    result = fuse_waste_objects([yolo_detection("mystery debris", 0.73)], [])

    assert result[0]["category"] == "Unknown"
    assert result[0]["category_source"] == "unknown"
    assert result[0]["source"] == "yolo"


def test_backend_mapping_overrides_matching_vlm_suggestion() -> None:
    result = fuse_waste_objects(
        [yolo_detection("plastic_bottle", 0.92)],
        [vlm_observation("plastic bottle", "high", "Bulky Waste")],
    )

    assert result[0]["category"] == "Recyclable Waste"
    assert result[0]["category_source"] == "mapping"
    assert result[0]["source"] == "yolo+vlm"


@pytest.mark.parametrize("confidence", [-0.01, 1.01, True, "high"])
def test_invalid_yolo_confidence_is_rejected(confidence: object) -> None:
    detection = yolo_detection("plastic_bottle", 0.5)
    detection["confidence"] = confidence

    with pytest.raises(FusionInputError, match="confidence"):
        fuse_waste_objects([detection], [])


def test_invalid_yolo_bounding_box_is_rejected() -> None:
    detection = yolo_detection("plastic_bottle", 0.9)
    detection["bounding_box"] = None

    with pytest.raises(FusionInputError, match="bounding_box"):
        fuse_waste_objects([detection], [])


def test_reversed_yolo_bounding_box_is_rejected() -> None:
    detection = yolo_detection("plastic_bottle", 0.9, (20, 2, 10, 40))

    with pytest.raises(FusionInputError, match="coordinate ordering"):
        fuse_waste_objects([detection], [])


def test_invalid_vlm_confidence_level_is_rejected() -> None:
    with pytest.raises(FusionInputError, match="confidence_level"):
        fuse_waste_objects([], [vlm_observation("mattress", "certain")])


def test_invalid_vlm_category_suggestion_is_rejected() -> None:
    with pytest.raises(FusionInputError, match="suggested_category"):
        fuse_waste_objects(
            [],
            [vlm_observation("mattress", "high", "Other")],
        )
