from pathlib import Path
from typing import Any

import pytest

from app.services.ai import waste_ai_service


DETECTION_RESULT: dict[str, Any] = {
    "success": True,
    "code": "WASTE_DETECTED",
    "message": "Supported waste objects were detected successfully.",
    "total_objects": 2,
    "counts": {"plastic_bottle": 1, "metal_can": 1},
    "detections": [
        {
            "class_name": "plastic_bottle",
            "class_id": 0,
            "confidence": 0.91,
            "display_name": "Plastic Bottle",
            "waste_category": "Recyclable Waste",
            "material": "Plastic",
            "recyclable": True,
            "recommended_handling": "Recycle appropriately.",
            "bounding_box": {"x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0},
        },
        {
            "class_name": "metal_can",
            "class_id": 1,
            "confidence": 0.82,
            "display_name": "Metal Can",
            "waste_category": "Recyclable Waste",
            "material": "Metal",
            "recyclable": True,
            "recommended_handling": "Recycle appropriately.",
            "bounding_box": {"x1": 5.0, "y1": 6.0, "x2": 7.0, "y2": 8.0},
        },
    ],
    "annotated_image_path": "storage/tmp/annotated/result.jpg",
}

REPORT = {
    "title": "Municipal Waste Report",
    "summary": "Two recyclable items were detected.",
    "waste_identified": "One plastic bottle and one metal can.",
    "recommended_action": "Separate, rinse, and recycle both items.",
    "environmental_concern": "Improper disposal may contribute to litter.",
}


def test_successfully_coordinates_detection_and_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "waste.jpg"
    received_report_input: object = None

    def fake_detector(path: str | Path, threshold: float) -> dict[str, Any]:
        assert path == image_path
        assert threshold == 0.42
        return DETECTION_RESULT

    def fake_reporter(detection: object) -> dict[str, str]:
        nonlocal received_report_input
        received_report_input = detection
        return REPORT

    monkeypatch.setattr(waste_ai_service, "detect_waste", fake_detector)
    monkeypatch.setattr(waste_ai_service, "generate_waste_report", fake_reporter)

    result = waste_ai_service.analyze_waste_image(image_path, 0.42)

    assert received_report_input is DETECTION_RESULT
    assert result == {
        "success": True,
        "original_image": str(image_path.resolve()),
        "annotated_image": "storage/tmp/annotated/result.jpg",
        "detection": {
            "total_objects": 2,
            "counts": {"plastic_bottle": 1, "metal_can": 1},
            "detections": DETECTION_RESULT["detections"],
        },
        "report": REPORT,
    }


def test_detection_failure_stops_before_report_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda *_args: {
            "success": False,
            "code": "NO_WASTE_DETECTED",
            "message": "No supported waste objects were detected in this image.",
        },
    )
    monkeypatch.setattr(
        waste_ai_service,
        "generate_waste_report",
        lambda *_args: pytest.fail("Ollama must not be called without detections."),
    )

    result = waste_ai_service.analyze_waste_image("empty.jpg")

    assert result == {
        "success": False,
        "code": "NO_WASTE_DETECTED",
        "message": "No supported waste objects were detected in this image.",
        "stage": "detection",
    }


def test_inconsistent_zero_detection_result_stops_before_report_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zero_result = {
        **DETECTION_RESULT,
        "total_objects": 0,
        "counts": {},
        "detections": [],
    }
    monkeypatch.setattr(waste_ai_service, "detect_waste", lambda *_args: zero_result)
    monkeypatch.setattr(
        waste_ai_service,
        "generate_waste_report",
        lambda *_args: pytest.fail("Ollama must not be called for zero objects."),
    )

    result = waste_ai_service.analyze_waste_image("empty.jpg")

    assert result["success"] is False
    assert result["code"] == "NO_WASTE_DETECTED"
    assert result["stage"] == "detection"


def test_report_failure_preserves_detection_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "waste.jpg"
    monkeypatch.setattr(
        waste_ai_service,
        "detect_waste",
        lambda *_args: DETECTION_RESULT,
    )
    monkeypatch.setattr(
        waste_ai_service,
        "generate_waste_report",
        lambda *_args: {
            "success": False,
            "code": "OLLAMA_TIMEOUT",
            "message": "Ollama did not respond within 30 seconds.",
        },
    )

    result = waste_ai_service.analyze_waste_image(image_path)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_TIMEOUT"
    assert result["stage"] == "report_generation"
    assert result["original_image"] == str(image_path.resolve())
    assert result["annotated_image"] == "storage/tmp/annotated/result.jpg"
    assert result["detection"]["total_objects"] == 2


def test_unexpected_detector_exception_returns_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_detector(*_args: object) -> object:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(waste_ai_service, "detect_waste", fail_detector)

    result = waste_ai_service.analyze_waste_image("waste.jpg")

    assert result == {
        "success": False,
        "code": "ANALYSIS_ERROR",
        "message": "Waste image analysis failed unexpectedly during detection.",
        "stage": "detection",
    }
