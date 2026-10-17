from __future__ import annotations

import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from florence_service.app import create_app
from florence_service.detector import normalize_detections
from florence_service.settings import load_settings


def picture(width=12, height=8, fmt="PNG", orientation=None) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    output = io.BytesIO()
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        image.save(output, format=fmt, exif=exif)
    else:
        image.save(output, format=fmt)
    return output.getvalue()


class FakeDetector:
    model = object()
    processor = object()
    device = "cpu"
    dtype_name = "float32"
    load_error = None
    calls = 0

    def load(self):
        self.calls += 1

    def detect(self, image):
        return [{"label": "bottle", "bounding_box": {
            "x1": 1.0, "y1": 1.0, "x2": float(image.width), "y2": float(image.height)
        }, "confidence": None}], [], 1


def test_box_clipping_and_invalid_values():
    parsed = {"<OD>": {"bboxes": [[-2, 1, 15, 9], [2, 2, 1, 5], [0, 0, float("nan"), 4]],
                       "labels": ["bottle", "bad", "nonfinite"]}}
    items, warnings = normalize_detections(parsed, 12, 8)
    assert items == [{"label": "bottle", "bounding_box": {
        "x1": 0.0, "y1": 1.0, "x2": 12.0, "y2": 8.0
    }, "confidence": None}]
    assert len(warnings) == 3
    with pytest.raises(ValueError, match="mismatched"):
        normalize_detections({"<OD>": {"bboxes": [[0, 0, 1, 1]], "labels": []}}, 12, 8)


def test_health_and_exif_corrected_detection():
    fake = FakeDetector()
    app = create_app(detector=fake)
    with TestClient(app) as client:
        health = client.get("/health").json()
        assert health["service_available"] is True
        assert health["model_ready"] is True
        result = client.post("/detect", files={"image": ("photo.jpg", picture(fmt="JPEG", orientation=6), "image/jpeg")})
    assert fake.calls == 1
    assert result.status_code == 200
    body = result.json()
    assert (body["image_width"], body["image_height"]) == (8, 12)
    assert body["device"] == "cpu"
    assert body["detections"][0]["confidence"] is None


def test_invalid_content_and_size_rejected_before_inference():
    fake = FakeDetector()
    settings = replace(load_settings(), max_upload_bytes=32)
    with TestClient(create_app(settings, fake)) as client:
        too_large = client.post("/detect", files={"image": ("photo.png", picture(), "image/png")})
    with TestClient(create_app(detector=fake)) as client:
        mismatch = client.post("/detect", files={"image": ("photo.jpg", picture(fmt="JPEG"), "image/png")})
    assert too_large.status_code == 413
    assert mismatch.status_code == 400


def test_inference_error_is_not_empty_success():
    class BrokenDetector(FakeDetector):
        def detect(self, image):
            raise RuntimeError("model failed")

    with TestClient(create_app(detector=BrokenDetector())) as client:
        result = client.post("/detect", files={"image": ("photo.png", picture(), "image/png")})
    assert result.status_code == 500
    assert result.json()["success"] is False
    assert result.json()["error"]["code"] == "INFERENCE_FAILED"


def test_config_rejects_remote_bind_and_unpinned_model(tmp_path):
    from dataclasses import asdict

    values = asdict(load_settings())
    path = tmp_path / "config.json"
    values["host"] = "0.0.0.0"
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(ValueError, match="loopback"):
        load_settings(path)
    values["host"] = "127.0.0.1"
    values["model_revision"] = "main"
    path.write_text(json.dumps(values), encoding="utf-8")
    with pytest.raises(ValueError, match="pinned"):
        load_settings(path)
