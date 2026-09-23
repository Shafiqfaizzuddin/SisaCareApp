import json

import httpx
import pytest

from app.services.ai.ollama_connectivity import (
    OllamaApiError,
    OllamaMalformedResponseError,
    OllamaModelNotInstalledError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    check_ollama_connection,
)


def test_successful_non_streaming_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://localhost:11434/api/generate"
        assert json.loads(request.content) == {
            "model": "test-model",
            "prompt": "Reply with exactly: Ollama connection successful.",
            "stream": False,
        }
        return httpx.Response(
            200,
            json={"response": "Ollama connection successful.", "done": True},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = check_ollama_connection(
            base_url="http://localhost:11434/",
            model="test-model",
            timeout_seconds=5,
            client=client,
        )

    assert result == "Ollama connection successful."


def test_unavailable_server_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OllamaUnavailableError):
            check_ollama_connection(
                base_url="http://localhost:11434",
                model="test-model",
                timeout_seconds=5,
                client=client,
            )


def test_timeout_is_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OllamaTimeoutError):
            check_ollama_connection(
                base_url="http://localhost:11434",
                model="test-model",
                timeout_seconds=5,
                client=client,
            )


def test_missing_model_is_reported() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            404,
            json={"error": "model 'missing-model' not found"},
        )
    )

    with httpx.Client(transport=transport) as client:
        with pytest.raises(OllamaModelNotInstalledError, match="missing-model"):
            check_ollama_connection(
                base_url="http://localhost:11434",
                model="missing-model",
                timeout_seconds=5,
                client=client,
            )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"done": True}),
        httpx.Response(200, json={"response": "", "done": True}),
        httpx.Response(200, json={"response": "partial", "done": False}),
    ],
)
def test_malformed_response_is_reported(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda _request: response)

    with httpx.Client(transport=transport) as client:
        with pytest.raises(OllamaMalformedResponseError):
            check_ollama_connection(
                base_url="http://localhost:11434",
                model="test-model",
                timeout_seconds=5,
                client=client,
            )


def test_other_api_error_is_reported() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(500, json={"error": "server failure"})
    )

    with httpx.Client(transport=transport) as client:
        with pytest.raises(OllamaApiError, match="HTTP 500"):
            check_ollama_connection(
                base_url="http://localhost:11434",
                model="test-model",
                timeout_seconds=5,
                client=client,
            )
