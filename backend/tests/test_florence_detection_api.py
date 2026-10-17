import httpx
from fastapi.testclient import TestClient

from app.api import florence_detection
from app.core.rate_limit import enforce_ai_analysis_rate_limit
from app.main import app


def test_authenticated_florence_proxy_preserves_detector_response(monkeypatch):
    app.dependency_overrides[enforce_ai_analysis_rate_limit] = lambda: {
        "id": "participant-1", "email": "member@example.com", "role": "user"
    }
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, files):
            captured["url"] = url
            captured["image"] = files["image"]
            return httpx.Response(200, json={
                "success": True, "analysis_id": "draft-1", "detections": [],
                "device": "cpu", "warnings": ["No objects detected"],
            })

    monkeypatch.setattr(florence_detection.httpx, "AsyncClient", FakeClient)
    try:
        response = TestClient(app).post(
            "/api/waste/florence/analyze",
            files={"image": ("example.png", b"image bytes", "image/png")},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["device"] == "cpu"
    assert captured["url"].endswith("/detect")
    assert captured["image"] == ("example.png", b"image bytes", "image/png")


def test_florence_proxy_requires_sign_in():
    response = TestClient(app).post(
        "/api/waste/florence/analyze",
        files={"image": ("example.png", b"image bytes", "image/png")},
    )
    assert response.status_code == 401
