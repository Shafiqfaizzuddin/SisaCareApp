from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings


def test_ai_configuration_has_project_relative_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.yolo_model_path == PROJECT_ROOT / "ai" / "models" / "best.pt"
    assert settings.yolo_confidence_threshold == 0.35
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.max_upload_size == 10 * 1024 * 1024
    assert settings.max_image_pixels == 40_000_000
    assert settings.ai_rate_limit_requests == 5
    assert settings.ai_rate_limit_window_seconds == 60
    assert settings.upload_dir == (
        PROJECT_ROOT / "backend" / "storage" / "tmp" / "uploads"
    )
    assert settings.annotated_output_dir == (
        PROJECT_ROOT / "backend" / "storage" / "tmp" / "annotated"
    )


def test_relative_ai_paths_are_resolved_from_project_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings(
        _env_file=None,
        yolo_model_path=Path("models/custom.pt"),
        upload_dir=Path("runtime/uploads"),
        annotated_output_dir=Path("runtime/annotated"),
    )

    assert settings.yolo_model_path == PROJECT_ROOT / "models" / "custom.pt"
    assert settings.upload_dir == PROJECT_ROOT / "runtime" / "uploads"
    assert settings.annotated_output_dir == PROJECT_ROOT / "runtime" / "annotated"


def test_ai_configuration_can_be_overridden_with_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YOLO_MODEL_PATH", "models/alternate.pt")
    monkeypatch.setenv("YOLO_CONFIDENCE_THRESHOLD", "0.6")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11500")
    monkeypatch.setenv("OLLAMA_MODEL", "custom-model")
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "2097152")
    monkeypatch.setenv("UPLOAD_DIR", "runtime/incoming")
    monkeypatch.setenv("ANNOTATED_OUTPUT_DIR", "runtime/results")

    settings = Settings(_env_file=None)

    assert settings.yolo_model_path == PROJECT_ROOT / "models" / "alternate.pt"
    assert settings.yolo_confidence_threshold == 0.6
    assert settings.ollama_base_url == "http://127.0.0.1:11500"
    assert settings.ollama_model == "custom-model"
    assert settings.max_upload_size == 2 * 1024 * 1024
    assert settings.upload_dir == PROJECT_ROOT / "runtime" / "incoming"
    assert settings.annotated_output_dir == PROJECT_ROOT / "runtime" / "results"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("yolo_confidence_threshold", -0.01),
        ("yolo_confidence_threshold", 1.01),
        ("max_upload_size", 0),
    ],
)
def test_invalid_ai_configuration_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_remote_ollama_requires_explicit_opt_in() -> None:
    with pytest.raises(ValidationError, match="OLLAMA_ALLOW_REMOTE"):
        Settings(_env_file=None, ollama_base_url="http://ollama.internal:11434")

    settings = Settings(
        _env_file=None,
        ollama_base_url="http://ollama.internal:11434",
        ollama_allow_remote=True,
    )

    assert settings.ollama_base_url == "http://ollama.internal:11434"


def test_cors_wildcard_is_rejected() -> None:
    settings = Settings(_env_file=None, cors_allowed_origins="*")

    with pytest.raises(ValueError, match="wildcard"):
        settings.allowed_cors_origins
