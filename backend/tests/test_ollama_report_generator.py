import json
import logging

import httpx
import pytest

from app.services.ai.ollama_report_generator import generate_waste_report


ANALYSIS_DATA = {
    "mode": "hybrid",
    "objects": [
        {
            "name": "plastic_bottle",
            "display_name": "Plastic Bottle",
            "category": "Recyclable Waste",
            "source": "yolo+vlm",
            "confidence": 0.91,
            "bounding_box": {"x1": 1, "y1": 2, "x2": 3, "y2": 4},
        }
    ],
    "grouped_objects": [
        {
            "name": "plastic_bottle",
            "label": "Pile of Plastic Bottles",
            "count": 3,
            "category": "Recyclable Waste",
            "sources": ["yolo", "vlm"],
            "average_yolo_confidence": 0.9,
        },
        {
            "name": "food_wrapper",
            "label": "Food Wrapper",
            "count": 1,
            "category": "Non-Recyclable",
            "sources": ["yolo"],
            "average_yolo_confidence": 0.82,
        },
        {
            "name": "mattress",
            "label": "Mattress",
            "count": 1,
            "category": "Bulky Waste",
            "sources": ["vlm"],
            "average_yolo_confidence": None,
        },
    ],
    "categories_detected": [
        "Recyclable Waste",
        "Non-Recyclable",
        "Bulky Waste",
    ],
    "scene_description": "A field that must not reach the report model.",
    "annotated_image": "annotated-output.jpg",
}

VALID_REPORT = {
    "title": "Municipal Waste Observation Report",
    "summary": (
        "The analysis identifies recyclable, non-recyclable, and bulky waste."
    ),
    "waste_identified": (
        "Pile of Plastic Bottles (count: 3); Food Wrapper (count: 1); "
        "Mattress (count: 1)"
    ),
    "recommended_action": (
        "The items should be handled according to their supplied waste categories."
    ),
    "environmental_concern": (
        "Improper handling may contribute to litter and material loss."
    ),
}


def ollama_response(report: object = VALID_REPORT) -> httpx.Response:
    return httpx.Response(
        200,
        json={"response": json.dumps(report), "done": True},
    )


def test_sends_only_sanitized_grouped_analysis_to_ollama(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["stream"] is False
        assert payload["options"] == {"temperature": 0}
        assert "images" not in payload
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
        facts = prompt.split("AUTHORITATIVE_BACKEND_FACTS_START\n", 1)[1].split(
            "\nAUTHORITATIVE_BACKEND_FACTS_END", 1
        )[0]
        assert json.loads(facts) == {
            "grouped_objects": [
                {
                    "label": "Pile of Plastic Bottles",
                    "count": 3,
                    "category": "Recyclable Waste",
                },
                {
                    "label": "Food Wrapper",
                    "count": 1,
                    "category": "Non-Recyclable",
                },
                {
                    "label": "Mattress",
                    "count": 1,
                    "category": "Bulky Waste",
                },
            ],
            "categories_detected": [
                "Recyclable Waste",
                "Non-Recyclable",
                "Bulky Waste",
            ],
        }
        for excluded in (
            "plastic_bottle",
            "bounding_box",
            "confidence",
            "sources",
            "scene_description",
            "annotated-output.jpg",
        ):
            assert excluded not in facts
        assert "No image is available to you" in prompt
        assert payload["keep_alive"] == "10m"
        assert "Do not infer, change, or override a category" in prompt
        assert "Preserve every supplied integer count exactly" in prompt
        return ollama_response()

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(
            ANALYSIS_DATA,
            base_url="http://localhost:11434",
            model="test-model",
            timeout_seconds=5,
            client=client,
        )

    assert result == VALID_REPORT
    assert "ollama_request_started group_count=3" in caplog.text
    assert "ollama_request_succeeded" in caplog.text
    assert "report_generation_completed" in caplog.text
    assert "plastic_bottle" not in caplog.text
    assert VALID_REPORT["summary"] not in caplog.text


def test_empty_grouped_analysis_is_not_sent_to_ollama() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Empty grouped analysis must not be sent to Ollama.")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(
            {"grouped_objects": [], "categories_detected": []},
            client=client,
        )

    assert result == {
        "success": False,
        "code": "NO_WASTE_DETECTED",
        "message": "A waste report cannot be generated without grouped waste objects.",
    }


@pytest.mark.parametrize(
    "analysis_data",
    [
        None,
        {},
        {"grouped_objects": "not-a-list", "categories_detected": []},
        {"grouped_objects": [], "categories_detected": "not-a-list"},
        {"grouped_objects": ["not-an-object"], "categories_detected": []},
        {
            "grouped_objects": [{"count": 1, "category": "Recyclable Waste"}],
            "categories_detected": ["Recyclable Waste"],
        },
        {
            "grouped_objects": [
                {"label": "Paper", "count": 0, "category": "Recyclable Waste"}
            ],
            "categories_detected": ["Recyclable Waste"],
        },
        {
            "grouped_objects": [
                {"label": "Paper", "count": True, "category": "Recyclable Waste"}
            ],
            "categories_detected": ["Recyclable Waste"],
        },
        {
            "grouped_objects": [
                {"label": "Paper", "count": 1, "category": "Garden Waste"}
            ],
            "categories_detected": ["Garden Waste"],
        },
        {
            "grouped_objects": [
                {"label": "Paper", "count": 1, "category": ["Recyclable Waste"]}
            ],
            "categories_detected": ["Recyclable Waste"],
        },
        {
            "grouped_objects": [
                {"label": "Paper", "count": 1, "category": "Recyclable Waste"}
            ],
            "categories_detected": ["Recyclable Waste", "Recyclable Waste"],
        },
        {
            "grouped_objects": [
                {"label": "Paper", "count": 1, "category": "Recyclable Waste"}
            ],
            "categories_detected": ["Bulky Waste"],
        },
    ],
)
def test_invalid_grouped_analysis_is_rejected(analysis_data: object) -> None:
    result = generate_waste_report(analysis_data)  # type: ignore[arg-type]

    assert result["success"] is False
    assert result["code"] == "INVALID_ANALYSIS_DATA"


def test_vlm_only_group_with_unknown_count_does_not_gain_a_quantity() -> None:
    analysis = {
        "grouped_objects": [
            {"label": "Mattress", "count": None, "category": "Bulky Waste"}
        ],
        "categories_detected": ["Bulky Waste"],
    }
    report = {
        "title": "Bulky Waste Observation",
        "summary": "Bulky waste is identified in the supplied analysis.",
        "waste_identified": "Mattress (count unavailable)",
        "recommended_action": "Appropriate bulky waste handling is recommended.",
        "environmental_concern": "Improper handling may create environmental risks.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["prompt"]
        assert '"count": null' in prompt
        return ollama_response(report)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert generate_waste_report(analysis, client=client) == report


def test_vlm_only_unknown_count_is_restored_from_grouped_facts() -> None:
    analysis = {
        "grouped_objects": [
            {"label": "Mattress", "count": None, "category": "Bulky Waste"}
        ],
        "categories_detected": ["Bulky Waste"],
    }
    report = {
        "title": "Bulky Waste Observation",
        "summary": "Bulky waste is identified in the supplied analysis.",
        "waste_identified": "Mattress (count: 1)",
        "recommended_action": "Appropriate bulky waste handling is recommended.",
        "environmental_concern": "Improper handling may create environmental risks.",
    }
    transport = httpx.MockTransport(lambda _request: ollama_response(report))

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(analysis, client=client)

    assert result == {
        **report,
        "waste_identified": "Mattress (count unavailable)",
    }


def test_model_paraphrase_is_replaced_with_canonical_labels_and_counts() -> None:
    report = {
        **VALID_REPORT,
        "waste_identified": (
            "One pile of bottles, three wrappers, and an old mattress."
        ),
    }
    transport = httpx.MockTransport(lambda _request: ollama_response(report))

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(ANALYSIS_DATA, client=client)

    assert result == VALID_REPORT


def test_uses_supplied_final_category_without_remapping() -> None:
    analysis = {
        "objects": [{"name": "ceramic_plant_pot", "category_source": "vlm"}],
        "grouped_objects": [
            {
                "name": "ceramic_plant_pot",
                "label": "Ceramic Plant Pot",
                "count": 1,
                "category": "Bulky Waste",
            }
        ],
        "categories_detected": ["Bulky Waste"],
    }
    report = {
        "title": "Bulky Waste Observation",
        "summary": "The supplied analysis identifies bulky waste.",
        "waste_identified": "Ceramic Plant Pot (count: 1)",
        "recommended_action": "Bulky waste handling is recommended.",
        "environmental_concern": "Improper handling may create environmental risks.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["prompt"]
        assert '"label": "Ceramic Plant Pot"' in prompt
        assert '"category": "Bulky Waste"' in prompt
        assert "ceramic_plant_pot" not in prompt
        assert "category_source" not in prompt
        return ollama_response(report)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert generate_waste_report(analysis, client=client) == report


def test_connection_error_returns_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(ANALYSIS_DATA, client=client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_UNAVAILABLE"
    assert "localhost" not in result["message"]


def test_timeout_returns_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_waste_report(ANALYSIS_DATA, client=client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_TIMEOUT"


def test_missing_model_returns_fallback() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(404, json={"error": "model not found"})
    )

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(
            ANALYSIS_DATA,
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
        result = generate_waste_report(ANALYSIS_DATA, client=client)

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
        result = generate_waste_report(ANALYSIS_DATA, client=client)

    assert result["success"] is False
    assert result["code"] == "OLLAMA_API_ERROR"
    assert "server failure" not in result["message"]


@pytest.mark.parametrize(
    "report",
    [
        {**VALID_REPORT, "summary": "The detected waste weighs 2 kg."},
        {**VALID_REPORT, "summary": "The waste occupies 5 liters."},
        {**VALID_REPORT, "summary": "The waste was collected by the municipal crew."},
        {**VALID_REPORT, "summary": "The waste was found at Main Street."},
        {**VALID_REPORT, "summary": "Four waste items were identified."},
        {**VALID_REPORT, "summary": "Paper is also visible in the image."},
        {
            **VALID_REPORT,
            "environmental_concern": "Improper disposal causes environmental harm.",
        },
    ],
)
def test_ungrounded_report_claims_are_rejected(report: dict[str, str]) -> None:
    transport = httpx.MockTransport(lambda _request: ollama_response(report))

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(ANALYSIS_DATA, client=client)

    assert result == {
        "success": False,
        "code": "INVALID_OLLAMA_RESPONSE",
        "message": "Ollama returned an invalid waste report response.",
    }


def test_category_absent_from_analysis_is_rejected() -> None:
    analysis = {
        "grouped_objects": [
            {"label": "Paper", "count": 1, "category": "Recyclable Waste"}
        ],
        "categories_detected": ["Recyclable Waste"],
    }
    report = {
        "title": "Waste Observation",
        "summary": "One recyclable waste item and Bulky Waste were identified.",
        "waste_identified": "Paper (count: 1)",
        "recommended_action": "Recycling is recommended.",
        "environmental_concern": "Improper handling may create environmental risks.",
    }
    transport = httpx.MockTransport(lambda _request: ollama_response(report))

    with httpx.Client(transport=transport) as client:
        result = generate_waste_report(analysis, client=client)

    assert result["code"] == "INVALID_OLLAMA_RESPONSE"
