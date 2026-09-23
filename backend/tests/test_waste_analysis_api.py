from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.api import waste_analysis
from app.main import app


client = TestClient(app)


SUCCESS_RESULT: dict[str, Any] = {
    "success": True,
    "original_image": "ignored-by-api.jpg",
    "annotated_image": "",
    "detection": {
        "total_objects": 1,
        "counts": {"plastic_bottle": 1},
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
            }
        ],
    },
    "report": {
        "title": "Municipal Waste Report",
        "summary": "One item was detected.",
        "waste_identified": "One plastic bottle.",
        "recommended_action": "Recycle the bottle.",
        "environmental_concern": "Improper disposal may contribute to litter.",
    },
}


def configure_temp_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path]:
    upload_dir = tmp_path / "uploads"
    annotated_dir = tmp_path / "annotated"
    upload_dir.mkdir()
    annotated_dir.mkdir()
    monkeypatch.setattr(waste_analysis, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(waste_analysis, "ANNOTATED_OUTPUT_DIR", annotated_dir)
    return upload_dir, annotated_dir


def test_analyze_endpoint_returns_browser_accessible_image_urls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_dir, annotated_dir = configure_temp_storage(monkeypatch, tmp_path)
    annotated_path = annotated_dir / "annotated-result.jpg"
    annotated_path.write_bytes(b"annotated")
    result = {**SUCCESS_RESULT, "annotated_image": str(annotated_path)}
    monkeypatch.setattr(waste_analysis, "analyze_waste_image", lambda _path: result)

    response = client.post(
        "/api/waste/analyze",
        files={"image": ("waste.jpg", b"image data", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["annotated_image"] == "/api/waste/annotated/annotated-result.jpg"
    assert payload["original_image"].startswith("/api/waste/uploads/upload-")
    assert len(list(upload_dir.glob("*.jpg"))) == 1


def test_no_detection_is_returned_without_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_temp_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(
        waste_analysis,
        "analyze_waste_image",
        lambda _path: {
            "success": False,
            "code": "NO_WASTE_DETECTED",
            "message": "No supported waste objects were detected in this image.",
            "stage": "detection",
        },
    )

    response = client.post(
        "/api/waste/analyze",
        files={"image": ("empty.png", b"image data", "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "NO_WASTE_DETECTED"


def test_unsupported_file_type_is_rejected_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        waste_analysis,
        "analyze_waste_image",
        lambda _path: pytest.fail("Unsupported uploads must not be analyzed."),
    )

    response = client.post(
        "/api/waste/analyze",
        files={"image": ("waste.gif", b"image data", "image/gif")},
    )

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"


def test_oversized_upload_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_temp_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(waste_analysis, "MAX_UPLOAD_SIZE", 4)
    monkeypatch.setattr(
        waste_analysis,
        "analyze_waste_image",
        lambda _path: pytest.fail("Oversized uploads must not be analyzed."),
    )

    response = client.post(
        "/api/waste/analyze",
        files={"image": ("large.webp", b"12345", "image/webp")},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "IMAGE_TOO_LARGE"
    assert list((tmp_path / "uploads").iterdir()) == []
