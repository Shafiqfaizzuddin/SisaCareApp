import base64
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.api import florence_analysis
from app.core.auth import require_authenticated_user
from app.core.rate_limit import enforce_ai_analysis_rate_limit
from app.main import app

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def _auth():
    app.dependency_overrides[enforce_ai_analysis_rate_limit] = lambda: {
        "id": "usr-204", "email": "member@example.com", "role": "user"
    }


def test_confirmed_item_rule_refresh_uses_central_mapping():
    app.dependency_overrides[require_authenticated_user] = lambda: {
        "id": "usr-204", "email": "member@example.com", "role": "user"
    }
    try:
        with TestClient(app) as client:
            response = client.post("/api/waste/classify", json={
                "label": "battery", "material": "Unknown", "condition_answers": {},
            })
        assert response.status_code == 200
        assert response.json()["category"] == "Hazardous Waste"
        assert response.json()["handling_guidance"]
        assert response.json()["station_material_key"] is None
    finally:
        app.dependency_overrides.pop(require_authenticated_user, None)


def test_analysis_uses_local_detector_without_location_and_preserves_unknowns(tmp_path, monkeypatch):
    _auth()
    monkeypatch.setattr(florence_analysis, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(florence_analysis, "PREVIEW_DIR", tmp_path / "previews")
    captured = {}

    def save_draft(**kwargs):
        captured.update(kwargs)
        return "draft-123"

    monkeypatch.setattr(florence_analysis, "create_analysis_draft", save_draft)

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, files):
            captured["url"] = url
            return httpx.Response(200, json={
                "success": True, "analysis_id": "service-1", "image_width": 1,
                "image_height": 1, "model_id": "microsoft/Florence-2-base",
                "model_revision": "pinned", "processing_time_ms": 19,
                "warnings": [], "detections": [
                    {"label": "mystery object", "bounding_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1}, "confidence": None},
                    {"label": "tree", "bounding_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1}, "confidence": None},
                ],
            })

    monkeypatch.setattr(florence_analysis.httpx, "AsyncClient", FakeClient)
    try:
        response = TestClient(app).post("/api/waste/analyze", files={"image": ("waste.png", PNG, "image/png")})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["analysis_id"] == "draft-123"
    assert data["provider"] == "florence2"
    assert [item["review_status"] for item in data["detections"]] == ["needs_confirmation", "background"]
    assert all(item["confidence"] is None for item in data["detections"])
    assert captured["detection"]["raw_detections"] == data["detections"]
    assert captured["report"] is None
    assert captured["url"].startswith("http://127.0.0.1:")
    assert Path(captured["annotated_image_path"]).exists()


def test_detector_unavailable_is_failure_and_cleans_upload(tmp_path, monkeypatch):
    _auth()
    monkeypatch.setattr(florence_analysis, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(florence_analysis, "PREVIEW_DIR", tmp_path / "previews")

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, files):
            raise httpx.ConnectError("service offline")

    monkeypatch.setattr(florence_analysis.httpx, "AsyncClient", FakeClient)
    try:
        response = TestClient(app).post("/api/waste/analyze", files={"image": ("waste.png", PNG, "image/png")})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["code"] == "FLORENCE_UNAVAILABLE"
    assert list((tmp_path / "uploads").iterdir()) == []


def test_no_objects_is_success_and_not_a_failure(tmp_path, monkeypatch):
    _auth()
    monkeypatch.setattr(florence_analysis, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(florence_analysis, "PREVIEW_DIR", tmp_path / "previews")
    monkeypatch.setattr(florence_analysis, "create_analysis_draft", lambda **kwargs: "empty-draft")

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, files):
            return httpx.Response(200, json={
                "success": True, "analysis_id": "service-empty", "image_width": 1,
                "image_height": 1, "model_id": "microsoft/Florence-2-base",
                "model_revision": "pinned", "processing_time_ms": 12,
                "warnings": ["No objects detected"], "detections": [],
            })

    monkeypatch.setattr(florence_analysis.httpx, "AsyncClient", FakeClient)
    try:
        response = TestClient(app).post("/api/waste/analyze", files={"image": ("empty.png", PNG, "image/png")})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["detections"] == []
    assert response.json()["warnings"] == ["No objects detected"]


def test_detector_timeout_is_distinct_from_no_objects(tmp_path, monkeypatch):
    _auth()
    monkeypatch.setattr(florence_analysis, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(florence_analysis, "PREVIEW_DIR", tmp_path / "previews")

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, files):
            raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(florence_analysis.httpx, "AsyncClient", FakeClient)
    try:
        response = TestClient(app).post("/api/waste/analyze", files={"image": ("waste.png", PNG, "image/png")})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 504
    assert response.json()["code"] == "FLORENCE_TIMEOUT"


def test_analysis_requires_sign_in():
    response = TestClient(app).post("/api/waste/analyze", files={"image": ("waste.png", PNG, "image/png")})
    assert response.status_code == 401


def test_active_detection_review_uses_versioned_rules():
    box = {"x1": 0, "y1": 0, "x2": 1, "y2": 1}
    bottle = florence_analysis._review_detection({"label": "bottle", "bounding_box": box}, 0)
    battery = florence_analysis._review_detection({"label": "battery", "bounding_box": box}, 1)
    food = florence_analysis._review_detection({"label": "food waste", "bounding_box": box}, 2)
    assert bottle["name"] == "bottle"
    assert bottle["suggested_category"] is None
    assert bottle["review_status"] == "needs_confirmation"
    assert bottle["rule_id"] == "WASTE-BOTTLE-v1"
    assert battery["suggested_category"] == "Hazardous Waste"
    assert battery["review_status"] == "needs_confirmation"
    assert battery["station_material_key"] is None
    assert food["suggested_category"] == "Non-Recyclable Waste"
    assert food["review_status"] == "likely_waste"
