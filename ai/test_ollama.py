"""Run a standalone connectivity check against a local Ollama server."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.core.config import Settings  # noqa: E402
from app.services.ai.ollama_connectivity import (  # noqa: E402
    OllamaApiError,
    OllamaMalformedResponseError,
    OllamaModelNotInstalledError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    check_ollama_connection,
)


def main() -> int:
    settings = Settings(_env_file=BACKEND_PATH / ".env")

    try:
        response_text = check_ollama_connection(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    except OllamaUnavailableError as exc:
        print(f"OLLAMA_UNAVAILABLE: {exc}", file=sys.stderr)
        return 2
    except OllamaTimeoutError as exc:
        print(f"OLLAMA_TIMEOUT: {exc}", file=sys.stderr)
        return 3
    except OllamaModelNotInstalledError as exc:
        print(f"MODEL_NOT_INSTALLED: {exc}", file=sys.stderr)
        return 4
    except OllamaMalformedResponseError as exc:
        print(f"MALFORMED_RESPONSE: {exc}", file=sys.stderr)
        return 5
    except OllamaApiError as exc:
        print(f"OLLAMA_API_ERROR: {exc}", file=sys.stderr)
        return 6

    print("Ollama response:")
    print(response_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
