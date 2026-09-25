import base64
import logging
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.api import waste_analysis
from app.core.auth import require_authenticated_user
from app.core.rate_limit import enforce_ai_analysis_rate_limit
from app.main import app


client = TestClient(app)
AUTHENTICATED_USER = {
    "id": "usr-204",
    "email": "member@example.com",
    "role": "user",
}
VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def authenticated_analysis() -> None:
    app.dependency_overrides[enforce_ai_analysis_rate_limit] = (
        lambda: AUTHENTICATED_USER
    )
    app.dependency_overrides[require_authenticated_user] = (
        lambda: AUTHENTICATED_USER
    )
    yield
    app.dependency_overrides.clear()


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
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.INFO)
    upload_dir, annotated_dir = configure_temp_storage(monkeypatch, tmp_path)
    annotated_path = annotated_dir / f"annotated-{'a' * 32}.jpg"
    annotated_path.write_bytes(b"annotated")
    result = {**SUCCESS_RESULT, "annotated_image": str(annotated_path)}
    monkeypatch.setattr(waste_analysis, "analyze_waste_image", lambda _path: result)
    monkeypatch.setattr(
        waste_analysis,
        "create_analysis_draft",
        lambda **_kwargs: "draft-123",
    )
    monkeypatch.setattr(
        waste_analysis,
        "analysis_draft_asset_belongs_to_user",
        lambda _user_id, _path: True,
    )

    response = client.post(
        "/api/waste/analyze",
        files={"image": ("waste.png", VALID_PNG, "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["analysis_id"] == "draft-123"
    assert payload["annotated_image"] == (
        f"/api/waste/annotated/annotated-{'a' * 32}.jpg"
    )
    assert payload["original_image"].startswith("/api/waste/uploads/upload-")
    assert len(list(upload_dir.glob("*.png"))) == 1

    original_response = client.get(payload["original_image"])
    annotated_response = client.get(payload["annotated_image"])
    assert original_response.status_code == 200
    assert original_response.headers["x-content-type-options"] == "nosniff"
    assert original_response.headers["cache-control"] == "private, no-store"
    assert annotated_response.status_code == 200
    assert annotated_response.headers["x-content-type-options"] == "nosniff"
    assert "analysis_request_started" in caplog.text
    assert "analysis_image_validation_completed" in caplog.text
    assert "analysis_request_completed" in caplog.text
    assert "detection_count=1" in caplog.text
    assert "waste.png" not in caplog.text
    assert AUTHENTICATED_USER["email"] not in caplog.text


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
        files={"image": ("empty.png", VALID_PNG, "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "NO_WASTE_DETECTED"
    assert list((tmp_path / "uploads").iterdir()) == []


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


def test_analyze_requires_authentication() -> None:
    app.dependency_overrides.pop(enforce_ai_analysis_rate_limit, None)
    app.dependency_overrides.pop(require_authenticated_user, None)

    response = client.post(
        "/api/waste/analyze",
        files={"image": ("waste.png", VALID_PNG, "image/png")},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication is required."


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("waste.svg", "image/svg+xml"),
        ("waste.exe", "image/png"),
        ("../waste.png", "image/png"),
        ("waste.jpg", "image/png"),
    ],
)
def test_unsafe_upload_metadata_is_rejected(
    filename: str,
    content_type: str,
) -> None:
    response = client.post(
        "/api/waste/analyze",
        files={"image": (filename, VALID_PNG, content_type)},
    )

    assert response.status_code == 415


def test_executable_content_spoofed_as_jpeg_is_rejected_and_deleted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_dir, _annotated_dir = configure_temp_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(
        waste_analysis,
        "analyze_waste_image",
        lambda _path: pytest.fail("Invalid image bytes must not reach YOLO."),
    )

    response = client.post(
        "/api/waste/analyze",
        files={"image": ("waste.jpg", b"MZ executable bytes", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"
    assert list(upload_dir.iterdir()) == []
