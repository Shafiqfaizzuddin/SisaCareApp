"""Controlled Florence outputs against real image decoding and current rules."""
from __future__ import annotations

import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api import florence_analysis
from app.core.rate_limit import enforce_ai_analysis_rate_limit
from app.main import app
from app.services.ai.classification_summary import summarize_detections


def _observation(label: str, index: int = 0) -> dict:
    return florence_analysis._review_detection({"label": label,
        "bounding_box": {"x1": index, "y1": 0, "x2": index + 1, "y2": 1}}, index)


@pytest.mark.parametrize(("label", "expected"), [
    ("food waste", "Organic"), ("plastic bottle", "Plastic"), ("newspaper", "Paper"),
    ("glass jar", "Glass"), ("scrap metal", "Metal"), ("mobile phone", "Electronic"),
    ("battery", "Hazardous"), ("clothing", "Other"), ("bottle", "Unknown"),
])
def test_normalized_category_uses_observed_item_and_material(label: str, expected: str) -> None:
    item = _observation(label)
    summary = summarize_detections([item])
    assert item["normalized_category"] == expected
    assert summary["denominator"] == 1
    assert summary["distribution"][0] == {"category": expected, "count": 1, "percentage": 100.0}
    assert item["confidence"] is None


def test_empty_and_tied_evidence_do_not_invent_dominance_or_severity() -> None:
    empty = summarize_detections([])
    assert empty["denominator"] == 0 and empty["distribution"] == []
    assert empty["dominant_category"] == "Unknown" and empty["severity"]["level"] == "Unknown"
    items = [_observation("plastic bottle", 0), _observation("glass jar", 1), _observation("tree", 2)]
    result = summarize_detections(items)
    assert result["denominator"] == 2 and result["background_excluded"] == 1
    assert result["dominant_category"] == "Unknown"
    assert [entry["percentage"] for entry in result["distribution"]] == [50.0, 50.0]
    assert result["confidence"]["category_probability"] is None


@pytest.mark.parametrize(("label", "severity"), [
    ("plastic bottle", "Low"), ("mobile phone", "High"),
    ("discarded sofa", "Medium"), ("battery", "High"), ("bottle", "Unknown"),
])
def test_severity_is_explained_by_handling_rules(label: str, severity: str) -> None:
    result = summarize_detections([_observation(label)])
    assert result["severity"]["level"] == severity
    assert result["severity"]["method"] == "rule_based_handling_priority_v1"
    assert result["severity"]["is_physical_measurement"] is False
    assert result["severity"]["reason"]


def test_florence_api_persists_original_boxes_and_distribution(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    app.dependency_overrides[enforce_ai_analysis_rate_limit] = lambda: {"id": "test-user", "role": "user"}
    monkeypatch.setattr(florence_analysis, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(florence_analysis, "PREVIEW_DIR", tmp_path / "previews")
    captured: dict = {}
    monkeypatch.setattr(florence_analysis, "create_analysis_draft", lambda **kwargs: captured.update(kwargs) or "analysis-1")
    labels = ["plastic bottle", "food waste", "battery", "tree", "mystery object"]
    boxes = [{"x1": index, "y1": 0, "x2": index + 1, "y2": 1} for index in range(len(labels))]

    class FakeClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, _url, files):
            return httpx.Response(200, json={"success": True, "analysis_id": "service-1",
                "image_width": 8, "image_height": 8, "model_id": "microsoft/Florence-2-base",
                "model_revision": "pinned", "processing_time_ms": 12, "warnings": [],
                "detections": [{"label": label, "bounding_box": box, "confidence": None}
                               for label, box in zip(labels, boxes)]})

    async def uncertain_visual(_image, _detection):
        return {"decision": "waste", "object_name": "mystery object", "material": "Unknown",
                "category": "Non-Recyclable Waste", "visual_justification": "Material is not identifiable.",
                "uncertain": True}

    monkeypatch.setattr(florence_analysis.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(florence_analysis, "resolve_detection", uncertain_visual)
    image = io.BytesIO(); Image.new("RGB", (8, 8), (40, 100, 60)).save(image, format="PNG")
    try:
        response = TestClient(app).post('/api/waste/analyze', files={"image": ("fixture.png", image.getvalue(), "image/png")})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json(); summary = body["classification_summary"]
    assert summary["denominator"] == 4 and summary["background_excluded"] == 1
    assert {entry["category"]: entry["count"] for entry in summary["distribution"]} == {
        "Organic": 1, "Plastic": 1, "Hazardous": 1, "Unknown": 1}
    assert all(entry["percentage"] == 25.0 for entry in summary["distribution"])
    assert summary["dominant_category"] == "Unknown"
    assert summary["severity"]["level"] == "High"
    assert summary["confidence"]["florence_detection_score"] is None
    original = captured["detection"]["model_detections"]
    assert [item["label"] for item in original] == labels
    assert [item["bounding_box"] for item in original] == boxes
    assert all("normalized_category" not in item for item in original)
    assert captured["detection"]["classification_summary"] == summary
