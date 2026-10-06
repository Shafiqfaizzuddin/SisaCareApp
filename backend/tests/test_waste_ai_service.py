import logging
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.services.ai import hybrid_analysis_service as waste_ai_service


def create_image(tmp_path: Path) -> Path:
    path = tmp_path / "waste.jpg"
    Image.new("RGB", (64, 48), "white").save(path)
    return path


def detection(
    name: str,
    confidence: float,
    class_id: int,
    x1: float,
) -> dict[str, Any]:
    return {
        "class_name": name,
        "class_id": class_id,
        "confidence": confidence,
        "bounding_box": {
            "x1": x1,
            "y1": 2.0,
            "x2": x1 + 10.0,
            "y2": 20.0,
        },
        "source": "yolo",
    }


def yolo_success(
    detections: list[dict[str, Any]],
    annotated_image: str = "annotated.jpg",
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in detections:
        name = item["class_name"]
        counts[name] = counts.get(name, 0) + 1
    return {
        "success": True,
        "code": "WASTE_DETECTED" if detections else "NO_WASTE_DETECTED",
        "message": "Detection completed.",
        "total_objects": len(detections),
        "counts": counts,
        "detections": detections,
        "annotated_image_path": annotated_image,
    }


def vlm_object(
    name: str,
    category: str,
    confidence_level: str = "high",
) -> dict[str, str]:
    return {
        "name": name,
        "display_name": name.replace("_", " ").title(),
        "suggested_category": category,
        "confidence_level": confidence_level,
        "reason": "The object is visibly present.",
    }


def test_both_services_work_and_return_full_hybrid_analysis(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.INFO)
    image_path = create_image(tmp_path)
    raw_detections = [
        detection("plastic_bottle", 0.95, 0, 1.0),
        detection("plastic bottle", 0.85, 0, 20.0),
    ]
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda path, threshold: (
            yolo_success(raw_detections, "annotated.jpg")
            if path == image_path.resolve() and threshold == 0.42
            else pytest.fail("Unexpected YOLO arguments.")
        ),
    )
    monkeypatch.setattr(
        waste_ai_service,
        "analyze_waste_image_with_vlm",
        lambda path: {
            "scene_description": "Bottles and a mattress are visible.",
            "objects": [
                vlm_object("Plastic Bottle", "Recyclable Waste"),
                vlm_object("mattress", "Bulky Waste", "medium"),
            ],
        }
        if path == image_path.resolve()
        else pytest.fail("Unexpected VLM image path."),
    )

    result = waste_ai_service.analyze_waste_image(image_path, 0.42)

    assert result["success"] is True
    assert result["yolo"]["available"] is True
    assert result["yolo"]["detections"] == raw_detections
    assert result["vlm"]["available"] is True
    assert result["analysis"]["mode"] == "hybrid"
    assert len(result["analysis"]["objects"]) == 3
    assert result["analysis"]["categories_detected"] == [
        "Recyclable Waste",
        "Bulky Waste",
    ]
    assert result["analysis"]["grouped_objects"] == [
        {
            "name": "plastic_bottle",
            "label": "Pile of Plastic Bottles",
            "count": 2,
            "category": "Recyclable Waste",
            "sources": ["yolo", "vlm"],
            "average_yolo_confidence": 0.9,
        },
        {
            "name": "mattress",
            "label": "Mattress",
            "count": None,
            "category": "Bulky Waste",
            "sources": ["vlm"],
            "average_yolo_confidence": None,
        },
    ]
    assert result["annotated_image"] == "annotated.jpg"
    assert "hybrid_yolo_completed duration_ms=" in caplog.text
    assert "hybrid_vlm_completed duration_ms=" in caplog.text
    assert "hybrid_fusion_completed duration_ms=" in caplog.text
    assert "total_duration_ms=" in caplog.text


def test_yolo_works_and_vlm_failure_uses_yolo_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_image(tmp_path)
    raw_detection = detection("drink_can", 0.88, 1, 1.0)
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda *_args: yolo_success([raw_detection]),
    )
    monkeypatch.setattr(
        waste_ai_service,
        "analyze_waste_image_with_vlm",
        lambda _path: {
            "success": False,
            "code": "OLLAMA_UNAVAILABLE",
            "message": "The Ollama vision service is unavailable.",
        },
    )

    result = waste_ai_service.analyze_waste_image(image_path)

    assert result["success"] is True
    assert result["analysis"]["mode"] == "yolo_only"
    assert result["vlm"]["available"] is False
    assert result["vlm"]["error"]["code"] == "OLLAMA_UNAVAILABLE"
    assert result["analysis"]["objects"][0]["source"] == "yolo"
    assert result["analysis"]["objects"][0]["bounding_box"] is not None


def test_yolo_failure_and_vlm_works_returns_vlm_only_without_boxes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_image(tmp_path)
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda *_args: {
            "success": False,
            "code": "MODEL_NOT_FOUND",
            "message": "The waste detection model file is missing.",
        },
    )
    monkeypatch.setattr(
        waste_ai_service,
        "analyze_waste_image_with_vlm",
        lambda _path: {
            "scene_description": "A mattress is visible.",
            "objects": [vlm_object("mattress", "Bulky Waste")],
        },
    )

    result = waste_ai_service.analyze_waste_image(image_path)

    assert result["success"] is True
    assert result["analysis"]["mode"] == "vlm_only"
    assert result["yolo"]["available"] is False
    assert result["analysis"]["objects"][0]["source"] == "vlm"
    assert result["analysis"]["objects"][0]["bounding_box"] is None
    assert result["analysis"]["grouped_objects"][0]["count"] is None
    assert result["annotated_image"] is None


def test_both_services_fail_returns_friendly_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_image(tmp_path)
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda *_args: {
            "success": False,
            "code": "MODEL_NOT_FOUND",
            "message": "The waste detection model file is missing.",
        },
    )
    monkeypatch.setattr(
        waste_ai_service,
        "analyze_waste_image_with_vlm",
        lambda _path: {
            "success": False,
            "code": "OLLAMA_UNAVAILABLE",
            "message": "The Ollama vision service is unavailable.",
        },
    )

    result = waste_ai_service.analyze_waste_image(image_path)

    assert result["success"] is False
    assert result["code"] == "AI_ANALYSIS_FAILED"
    assert result["analysis"] == {
        "mode": "unavailable",
        "objects": [],
        "grouped_objects": [],
        "categories_detected": [],
    }
    assert result["yolo"]["error"]["code"] == "MODEL_NOT_FOUND"
    assert result["vlm"]["error"]["code"] == "OLLAMA_UNAVAILABLE"


def test_both_services_return_no_waste(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_image(tmp_path)
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda *_args: yolo_success([], "annotated-empty.jpg"),
    )
    monkeypatch.setattr(
        waste_ai_service,
        "analyze_waste_image_with_vlm",
        lambda _path: {
            "scene_description": "No recognizable waste is visible.",
            "objects": [],
        },
    )

    result = waste_ai_service.analyze_waste_image(image_path)

    assert result["success"] is False
    assert result["code"] == "NO_WASTE_DETECTED"
    assert result["analysis"]["mode"] == "hybrid"
    assert result["analysis"]["objects"] == []
    assert result["annotated_image"] == "annotated-empty.jpg"


def test_invalid_image_stops_before_both_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "invalid.jpg"
    image_path.write_bytes(b"not an image")
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda *_args: pytest.fail("YOLO must not receive an invalid image."),
    )
    monkeypatch.setattr(
        waste_ai_service,
        "analyze_waste_image_with_vlm",
        lambda _path: pytest.fail("VLM must not receive an invalid image."),
    )

    result = waste_ai_service.analyze_waste_image(image_path)

    assert result["success"] is False
    assert result["code"] == "INVALID_IMAGE"
    assert result["stage"] == "validation"
    assert result["yolo"]["available"] is False
    assert result["vlm"]["available"] is False
