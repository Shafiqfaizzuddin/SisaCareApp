import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from app.services.ai.vlm_analyzer import (
    VLM_RESPONSE_JSON_SCHEMA,
    analyze_waste_image_with_vlm,
)


VALID_OUTPUT = {
    "scene_description": "Discarded packaging is visible on a paved surface.",
    "objects": [
        {
            "name": "plastic bottle",
            "display_name": "Plastic Bottle",
            "suggested_category": "Recyclable Waste",
            "confidence_level": "high",
            "reason": "A transparent bottle with a cap is clearly visible.",
        },
        {
            "name": "food wrapper",
            "display_name": "Food Wrapper",
            "suggested_category": "Non-Recyclable",
            "confidence_level": "medium",
            "reason": "A small flexible printed wrapper is visible nearby.",
        },
    ],
}


def create_image(tmp_path: Path, name: str = "waste.jpg") -> Path:
    path = tmp_path / name
    Image.new("RGB", (64, 48), "white").save(path)
    return path


def ollama_response(output: object = VALID_OUTPUT) -> httpx.Response:
    return httpx.Response(
        200,
        json={"response": json.dumps(output), "done": True},
    )


def analyze(
    image_path: Path,
    client: httpx.Client,
    *,
    model: str = "test-vision-model",
) -> dict[str, Any]:
    return analyze_waste_image_with_vlm(
        image_path,
        base_url="http://localhost:11434",
        model=model,
        timeout_seconds=5,
        client=client,
    )


def test_sends_image_to_ollama_and_returns_strict_structured_output(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.INFO)
    image_path = create_image(tmp_path)
    image_bytes = image_path.read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://localhost:11434/api/generate"
        payload = json.loads(request.content)
        assert payload["model"] == "test-vision-model"
        assert payload["stream"] is False
        assert payload["options"] == {"temperature": 0}
        assert payload["keep_alive"] == "10m"
        assert payload["format"] == VLM_RESPONSE_JSON_SCHEMA
        assert len(payload["images"]) == 1
        assert base64.b64decode(payload["images"][0]) == image_bytes
        prompt = payload["prompt"]
        assert "visibly present" in prompt
        assert "Do not invent" in prompt
        assert "Do not estimate weight" in prompt
        assert "Do not write a user-facing waste report" in prompt
        assert "Non-Recyclable" in prompt
        assert "Unknown" in prompt
        return ollama_response()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = analyze(image_path, client)

    assert result == VALID_OUTPUT
    assert "vlm_analysis_completed object_count=2" in caplog.text
    assert str(image_path) not in caplog.text
    assert "test-vision-model" not in caplog.text
    assert base64.b64encode(image_bytes).decode("ascii") not in caplog.text


def test_allows_empty_object_list_when_no_waste_is_identifiable(tmp_path: Path) -> None:
    image_path = create_image(tmp_path)
    output = {
        "scene_description": "An empty paved surface is visible.",
        "objects": [],
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: ollama_response(output))
    ) as client:
        result = analyze(image_path, client)

    assert result == output


def test_unconfigured_vision_model_is_reported_before_ollama_call(
    tmp_path: Path,
) -> None:
    image_path = create_image(tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("Ollama must not be called without a model.")
        )
    ) as client:
        result = analyze(image_path, client, model="")

    assert result == {
        "success": False,
        "code": "OLLAMA_VISION_MODEL_NOT_CONFIGURED",
        "message": "The Ollama vision model is not configured.",
    }


def test_ollama_unavailable_is_reported(tmp_path: Path) -> None:
    image_path = create_image(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = analyze(image_path, client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_UNAVAILABLE"


def test_ollama_timeout_is_reported(tmp_path: Path) -> None:
    image_path = create_image(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = analyze(image_path, client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_TIMEOUT"


def test_missing_vision_model_is_reported(tmp_path: Path) -> None:
    image_path = create_image(tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(404, json={"error": "model not found"})
        )
    ) as client:
        result = analyze(image_path, client)

    assert result == {
        "success": False,
        "code": "OLLAMA_VISION_MODEL_NOT_INSTALLED",
        "message": "The configured Ollama vision model is unavailable.",
    }


def test_other_ollama_error_is_reported_without_response_details(
    tmp_path: Path,
) -> None:
    image_path = create_image(tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                500,
                json={"error": "private upstream detail"},
            )
        )
    ) as client:
        result = analyze(image_path, client)

    assert result == {
        "success": False,
        "code": "OLLAMA_API_ERROR",
        "message": "The Ollama vision service returned an error.",
    }
    assert "private upstream detail" not in result["message"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"response": "not-json", "done": True}),
    ],
)
def test_invalid_json_is_reported(
    response: httpx.Response,
    tmp_path: Path,
) -> None:
    image_path = create_image(tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: response)
    ) as client:
        result = analyze(image_path, client)

    assert result["success"] is False
    assert result["code"] == "INVALID_VLM_JSON"


@pytest.mark.parametrize(
    "output",
    [
        [],
        {"scene_description": "Visible scene."},
        {
            "scene_description": "Visible scene.",
            "objects": [],
            "extra": "not allowed",
        },
        {"scene_description": "", "objects": []},
        {
            "scene_description": "Visible scene.",
            "objects": [
                {
                    **VALID_OUTPUT["objects"][0],
                    "suggested_category": "Hazardous Waste",
                }
            ],
        },
        {
            "scene_description": "Visible scene.",
            "objects": [
                {
                    **VALID_OUTPUT["objects"][0],
                    "confidence_level": "certain",
                }
            ],
        },
        {
            "scene_description": "Visible scene.",
            "objects": [{**VALID_OUTPUT["objects"][0], "name": "trash"}],
        },
        {
            "scene_description": "Visible scene.",
            "objects": [{**VALID_OUTPUT["objects"][0], "count": 3}],
        },
    ],
)
def test_malformed_output_is_rejected(output: object, tmp_path: Path) -> None:
    image_path = create_image(tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: ollama_response(output))
    ) as client:
        result = analyze(image_path, client)

    assert result["success"] is False
    assert result["code"] == "MALFORMED_VLM_OUTPUT"


def test_unsupported_image_is_rejected_before_ollama_call(tmp_path: Path) -> None:
    image_path = create_image(tmp_path, "waste.gif")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("Unsupported images must not reach Ollama.")
        )
    ) as client:
        result = analyze(image_path, client)

    assert result == {
        "success": False,
        "code": "UNSUPPORTED_FILE_TYPE",
        "message": "Unsupported file type. Supported types are JPEG, PNG, and WEBP.",
    }


def test_corrupted_image_is_rejected_before_ollama_call(tmp_path: Path) -> None:
    image_path = tmp_path / "corrupted.jpg"
    image_path.write_bytes(b"not image data")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("Invalid images must not reach Ollama.")
        )
    ) as client:
        result = analyze(image_path, client)

    assert result["success"] is False
    assert result["code"] == "INVALID_IMAGE"
