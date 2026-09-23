"""Connectivity check for the local Ollama generate API."""

from __future__ import annotations

from typing import Any

import httpx


TEST_PROMPT = "Reply with exactly: Ollama connection successful."


class OllamaConnectivityError(RuntimeError):
    """Base error for Ollama connectivity checks."""


class OllamaUnavailableError(OllamaConnectivityError):
    """Raised when the Ollama server cannot be reached."""


class OllamaTimeoutError(OllamaConnectivityError):
    """Raised when Ollama does not respond before the configured timeout."""


class OllamaModelNotInstalledError(OllamaConnectivityError):
    """Raised when Ollama cannot find the configured model."""


class OllamaApiError(OllamaConnectivityError):
    """Raised when Ollama returns an unexpected HTTP error."""


class OllamaMalformedResponseError(OllamaConnectivityError):
    """Raised when Ollama returns an invalid non-streaming response."""


def _api_error_detail(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return response.text.strip() or "No error details were returned."

    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return "No error details were returned."


def check_ollama_connection(
    *,
    base_url: str,
    model: str,
    timeout_seconds: float,
    client: httpx.Client | None = None,
) -> str:
    """Send a non-streaming test prompt and return Ollama's response text."""
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": TEST_PROMPT,
        "stream": False,
    }
    owns_client = client is None
    active_client = client or httpx.Client(timeout=timeout_seconds)

    try:
        try:
            response = active_client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama did not respond within {timeout_seconds:g} seconds."
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaUnavailableError(
                f"Could not connect to Ollama at {base_url}."
            ) from exc

        if response.status_code == 404:
            detail = _api_error_detail(response)
            raise OllamaModelNotInstalledError(
                f"Ollama model '{model}' is not installed or unavailable: {detail}"
            )
        if response.is_error:
            detail = _api_error_detail(response)
            raise OllamaApiError(
                f"Ollama returned HTTP {response.status_code}: {detail}"
            )

        try:
            response_data: Any = response.json()
        except ValueError as exc:
            raise OllamaMalformedResponseError(
                "Ollama returned a response that is not valid JSON."
            ) from exc

        if not isinstance(response_data, dict):
            raise OllamaMalformedResponseError(
                "Ollama returned JSON with an unexpected structure."
            )

        generated_text = response_data.get("response")
        if not isinstance(generated_text, str) or not generated_text.strip():
            raise OllamaMalformedResponseError(
                "Ollama response is missing a non-empty 'response' field."
            )
        if response_data.get("done") is not True:
            raise OllamaMalformedResponseError(
                "Ollama response is missing the completed 'done' status."
            )

        return generated_text.strip()
    finally:
        if owns_client:
            active_client.close()
