"""Local visual resolution is schema checked and never fabricates a category."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app.services.ai import visual_fallback
from app.services.ai.visual_fallback import VisualFallbackError, resolve_detection, resolve_batch
from app.services.ai.waste_rules import classify_item, load_rules
from app.repositories.reports import _build_review_confirmation


def _settings(model="qwen2.5vl:3b"):
    return SimpleNamespace(ollama_vision_model=model, ollama_base_url="http://127.0.0.1:11434",
                           ollama_vision_timeout_seconds=10, ollama_keep_alive="1m")


class FakeClient:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.payloads = []

    async def post(self, url, json):
        self.payloads.append(json)
        result = next(self.outputs)
        return httpx.Response(200, json={"done": True, "response": result})


def _detection(label="bottle"):
    return {"label": label, "bounding_box": {"x1": 10, "y1": 10, "x2": 30, "y2": 30}}


def _answer(name="glass bottle", category="Recyclable Waste", decision="waste"):
    return json.dumps({"decision": decision, "object_name": name, "material": "Glass",
                       "category": category, "visual_justification": "Visible glass container.", "uncertain": False})


def test_specific_policy_aliases_and_hazardous_precedence():
    load_rules.cache_clear()
    examples = {"plastic bottles": "Recyclable Waste", "tin can": "Recyclable Waste",
                "plastic shopping bag": "Non-Recyclable Waste", "battery": "Hazardous Waste",
                "aerosol can": "Hazardous Waste", "pesticide bottle": "Hazardous Waste"}
    for label, expected in examples.items():
        assert classify_item(label)["category"] == expected
    assert classify_item("bottle")["category"] is None
    assert classify_item("can")["category"] is None
    assert classify_item("unmapped object")["category"] is None
    assert classify_item("aerosol can")["canonical_name"] != classify_item("food can")["canonical_name"]
    assert classify_item("pesticide bottle")["canonical_name"] != classify_item("plastic bottle")["canonical_name"]


def test_generic_bottle_uses_original_and_padded_crop(monkeypatch):
    monkeypatch.setattr(visual_fallback, "get_settings", _settings)
    client = FakeClient([_answer()])
    result = asyncio.run(resolve_detection(Image.new("RGB", (64, 64), "white"), _detection(), client=client))
    assert result["object_name"] == "glass bottle"
    assert len(client.payloads) == 1
    assert len(client.payloads[0]["images"]) == 2
    assert client.payloads[0]["model"] == "qwen2.5vl:3b"


def test_invalid_visual_output_retries_then_fails(monkeypatch):
    monkeypatch.setattr(visual_fallback, "get_settings", _settings)
    client = FakeClient(['{"category":"Hazardous Waste"}', '{"decision":"waste"}'])
    with pytest.raises(VisualFallbackError, match="invalid data") as error:
        asyncio.run(resolve_detection(Image.new("RGB", (64, 64)), _detection("unknown item"), client=client))
    assert error.value.code == "VISION_INVALID_OUTPUT"
    assert len(client.payloads) == 2


def test_text_model_is_not_used_as_vision_fallback(monkeypatch):
    monkeypatch.setattr(visual_fallback, "get_settings", lambda: _settings(""))
    with pytest.raises(VisualFallbackError) as error:
        asyncio.run(resolve_detection(Image.new("RGB", (64, 64)), _detection()))
    assert error.value.code == "VISION_MODEL_NOT_CONFIGURED"


def test_visually_conflicting_specific_rule_is_rejected(monkeypatch):
    monkeypatch.setattr(visual_fallback, "get_settings", _settings)
    client = FakeClient([_answer("aerosol can", "Recyclable Waste"),
                         _answer("aerosol can", "Recyclable Waste")])
    with pytest.raises(VisualFallbackError) as error:
        asyncio.run(resolve_detection(Image.new("RGB", (64, 64)), _detection("can"), client=client))
    assert error.value.code == "VISION_INVALID_OUTPUT"


def test_batch_preserves_ids_and_rejects_omissions(monkeypatch):
    monkeypatch.setattr(visual_fallback, "get_settings", _settings)
    detections = [{"id": "det-0", **_detection("bottle")},
                  {"id": "det-1", **_detection("can")}]
    first = {"detection_id": "det-0", **json.loads(_answer())}
    second = {"detection_id": "det-1", **json.loads(_answer("aerosol can", "Hazardous Waste"))}
    client = FakeClient([json.dumps({"results": [first, second]})])
    results = asyncio.run(resolve_batch(Image.new("RGB", (64, 64)), detections, client=client))
    assert list(results) == ["det-0", "det-1"]
    assert results["det-1"]["category"] == "Hazardous Waste"
    assert len(client.payloads[0]["images"]) == 3
    invalid = FakeClient([json.dumps({"results": [first]}), json.dumps({"results": [first]})])
    with pytest.raises(VisualFallbackError) as error:
        asyncio.run(resolve_batch(Image.new("RGB", (64, 64)), detections, client=invalid))
    assert error.value.code == "VISION_INVALID_OUTPUT"


def test_visual_bulky_assessment_persists_without_claiming_user_confirmation():
    detection = {"id": "det-0", "label": "chair", "name": "chair", "material": "Mixed Furniture Material",
                 "suggested_category": "Bulky Waste", "classification_source": "vision",
                 "needs_confirmation": False, "visual_assessment": {"decision": "waste"}}
    review = {"id": "det-0", "source_detection_id": "det-0", "disposition": "waste",
              "corrected_label": "Chair", "material": "Mixed Furniture Material",
              "category": "Bulky Waste", "condition_answers": {}, "quantity": None}
    confirmed = {"review_id": "det-0", "name": "Chair", "material": "Mixed Furniture Material",
                 "category": "Bulky Waste", "condition_answers": {}, "quantity": None}
    result = _build_review_confirmation(json.dumps({"provider": "florence2", "raw_detections": [detection]}),
                                        {"reviewed_detections": [review], "confirmed_items": [confirmed]})
    assert result["final_confirmed_items"][0]["classification_source"] == "vision"
    assert result["final_confirmed_items"][0]["independently_verified"] is False
