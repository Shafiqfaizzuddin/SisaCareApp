import json
import logging

import httpx
import pytest

from app.services.ai.ollama_report_generator import generate_waste_report


DETECTION_DATA = {
    "total_objects": 3,
    "counts": {"plastic_bottle": 2, "metal_can": 1},
    "detections": [
        {
            "class_name": "plastic_bottle",
            "class_id": 0,
            "confidence": 0.91,
            "waste_category": "Caller supplied value must not be trusted",
            "bounding_box": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
        },
        {
            "class_name": "plastic_bottle",
            "class_id": 0,
            "confidence": 0.84,
            "bounding_box": {"x1": 5, "y1": 6, "x2": 7, "y2": 8},
        },
        {
            "class_name": "metal_can",
            "class_id": 1,
            "confidence": 0.77,
            "bounding_box": {"x1": 9, "y1": 10, "x2": 11, "y2": 12},
        },
    ],
}

VALID_REPORT = {
    "title": "Municipal Waste Observation Report",
    "summary": "Three recyclable items were detected.",
    "waste_identified": "Two plastic bottles and one metal can.",
    "recommended_action": "Separate, rinse, and recycle the detected items.",
    "environmental_concern": "Improper disposal may contribute to litter.",
}


def ollama_response(report: object = VALID_REPORT) -> httpx.Response:
    return httpx.Response(
        200,
        json={"response": json.dumps(report), "done": True},
    )


def test_generates_valid_report_from_sanitized_yolo_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["stream"] is False
        assert payload["options"] == {"temperature": 0}
        assert payload["format"] == {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "summary": {"type": "string", "minLength": 1},
                "waste_identified": {"type": "string", "minLength": 1},
                "recommended_action": {"type": "string", "minLength": 1},
                "environmental_concern": {"type": "string", "minLength": 1},
            },
            "required": [
                "title",
                "summary",
                "waste_identified",
                "recommended_action",
                "environmental_concern",
            ],
            "additionalProperties": False,
        }

        prompt = payload["prompt"]
        assert '"plastic_bottle": 2' in prompt
        assert '"metal_can": 1' in prompt
        assert '"backend_total_objects": 3' in prompt
        assert '"object_count": 2' in prompt
        assert '"waste_category": "Recyclable Waste"' in prompt
        assert "Caller supplied value must not be trusted" not in prompt
        assert "bounding_box" not in prompt
        assert "annotated_image" not in prompt
        assert '"confidence"' not in prompt
        assert "only permitted quantities" in prompt
        assert "Do not mention or invent a location" in prompt
        assert "has already happened" in prompt
        assert "possible or conditional impact" in prompt
        return ollama_response()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(
            DETECTION_DATA,
            base_url="http://localhost:11434",
            model="test-model",
            timeout_seconds=5,
            client=client,
        )

    assert result == VALID_REPORT
    assert "ollama_request_started detection_count=3" in caplog.text
    assert "ollama_request_succeeded" in caplog.text
    assert "report_generation_completed" in caplog.text
    assert "plastic_bottle" not in caplog.text
    assert VALID_REPORT["summary"] not in caplog.text


def test_empty_detection_list_is_not_sent_to_ollama() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Empty detections must not be sent to Ollama.")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(
            {"total_objects": 0, "counts": {}, "detections": []},
            client=client,
        )

    assert result == {
        "success": False,
        "code": "NO_WASTE_DETECTED",
        "message": "A waste report cannot be generated without YOLO detections.",
    }


@pytest.mark.parametrize(
    "detection_data",
    [
        {},
        {"detections": "not-a-list"},
        {"detections": ["not-an-object"]},
        {"detections": [{"confidence": 0.8}]},
        {"detections": [{"class_name": "paper", "confidence": 2.0}]},
    ],
)
def test_invalid_detection_data_is_rejected(detection_data: dict[str, object]) -> None:
    result = generate_waste_report(detection_data)

    assert result["success"] is False
    assert result["code"] == "INVALID_DETECTION_DATA"


def test_connection_error_returns_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(DETECTION_DATA, client=client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_UNAVAILABLE"
    assert "localhost" not in result["message"]


def test_timeout_returns_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(DETECTION_DATA, client=client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_TIMEOUT"


def test_missing_model_returns_fallback() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(404, json={"error": "model not found"})
    )

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(
            DETECTION_DATA,
            model="missing-model",
            client=client,
        )

    assert result["success"] is False
    assert result["code"] == "OLLAMA_MODEL_NOT_INSTALLED"
    assert "missing-model" not in result["message"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"response": "{}", "done": False}),
        httpx.Response(200, json={"response": "not-json", "done": True}),
        ollama_response({"title": "Missing required fields"}),
        ollama_response({**VALID_REPORT, "extra": "not allowed"}),
        ollama_response({**VALID_REPORT, "summary": ""}),
    ],
)
def test_invalid_ollama_response_returns_fallback(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda _request: response)

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(DETECTION_DATA, client=client)

    assert result == {
        "success": False,
        "code": "INVALID_OLLAMA_RESPONSE",
        "message": "Ollama returned an invalid waste report response.",
    }


def test_api_error_returns_fallback() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(500, json={"error": "server failure"})
    )

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(DETECTION_DATA, client=client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_API_ERROR"
    assert "server failure" not in result["message"]


@pytest.mark.parametrize(
    "report",
    [
        {
            **VALID_REPORT,
            "summary": "The detected waste weighs 2 kg.",
        },
        {
            **VALID_REPORT,
            "summary": "The waste was collected by the municipal crew.",
        },
        {
            **VALID_REPORT,
            "summary": "The waste was found at Main Street.",
        },
        {
            **VALID_REPORT,
            "summary": "Four recyclable items were detected.",
        },
        {
            **VALID_REPORT,
            "waste_identified": "Two plastic bottles, one can, and paper.",
        },
        {
            **VALID_REPORT,
            "environmental_concern": "Improper disposal causes environmental harm.",
        },
    ],
)
def test_ungrounded_report_claims_are_rejected(report: dict[str, str]) -> None:
    transport = httpx.MockTransport(lambda _request: ollama_response(report))

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(DETECTION_DATA, client=client)

    assert result == {
        "success": False,
        "code": "INVALID_OLLAMA_RESPONSE",
        "message": "Ollama returned an invalid waste report response.",
    }
