from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings


def test_ai_configuration_has_project_relative_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.yolo_model_path == PROJECT_ROOT / "ai" / "models" / "expV2.pt"
    assert settings.yolo_confidence_threshold == 0.35
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.max_upload_size == 10 * 1024 * 1024
    assert settings.max_image_pixels == 40_000_000
    assert settings.ai_rate_limit_requests == 5
    assert settings.ai_rate_limit_window_seconds == 60
    assert settings.tomtom_api_key.get_secret_value() == ""
    assert settings.tomtom_timeout_seconds == 8.0
    assert settings.tomtom_country_set == "MY"
    assert settings.location_rate_limit_requests == 30
    assert settings.upload_dir == (
        PROJECT_ROOT / "backend" / "storage" / "tmp" / "uploads"
    )
    assert settings.annotated_output_dir == (
        PROJECT_ROOT / "backend" / "storage" / "tmp" / "annotated"
    )
    assert settings.database_path == (
        PROJECT_ROOT / "backend" / "storage" / "sisacare.db"
    )
    assert settings.report_assets_dir == (
        PROJECT_ROOT / "backend" / "storage" / "reports"
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
        database_path=Path("runtime/database.db"),
        report_assets_dir=Path("runtime/reports"),
    )

    assert settings.yolo_model_path == PROJECT_ROOT / "models" / "custom.pt"
    assert settings.upload_dir == PROJECT_ROOT / "runtime" / "uploads"
    assert settings.annotated_output_dir == PROJECT_ROOT / "runtime" / "annotated"
    assert settings.database_path == PROJECT_ROOT / "runtime" / "database.db"
    assert settings.report_assets_dir == PROJECT_ROOT / "runtime" / "reports"


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
    monkeypatch.setenv("DATABASE_PATH", "runtime/database.db")
    monkeypatch.setenv("REPORT_ASSETS_DIR", "runtime/reports")
    monkeypatch.setenv("TOMTOM_API_KEY", "test-tomtom-key")
    monkeypatch.setenv("TOMTOM_COUNTRY_SET", "MY,SG")

    settings = Settings(_env_file=None)

    assert settings.yolo_model_path == PROJECT_ROOT / "models" / "alternate.pt"
    assert settings.yolo_confidence_threshold == 0.6
    assert settings.ollama_base_url == "http://127.0.0.1:11500"
    assert settings.ollama_model == "custom-model"
    assert settings.max_upload_size == 2 * 1024 * 1024
    assert settings.upload_dir == PROJECT_ROOT / "runtime" / "incoming"
    assert settings.annotated_output_dir == PROJECT_ROOT / "runtime" / "results"
    assert settings.database_path == PROJECT_ROOT / "runtime" / "database.db"
    assert settings.report_assets_dir == PROJECT_ROOT / "runtime" / "reports"
    assert settings.tomtom_api_key.get_secret_value() == "test-tomtom-key"
    assert settings.tomtom_country_set == "MY,SG"


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
