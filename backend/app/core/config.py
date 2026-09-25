from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"


class Settings(BaseSettings):
    app_name: str = "SisaCare.AI API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    yolo_model_path: Path = Path("ai/models/best.pt")
    yolo_confidence_threshold: float = Field(default=0.35, ge=0.0, le=1.0)

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_seconds: float = Field(default=30.0, gt=0.0)
    ollama_allow_remote: bool = False

    max_upload_size: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    upload_dir: Path = Path("backend/storage/tmp/uploads")
    annotated_output_dir: Path = Path("backend/storage/tmp/annotated")

    supabase_url: str = ""
    supabase_publishable_key: str = ""
    cors_allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173"
    )
    ai_rate_limit_requests: int = Field(default=5, gt=0)
    ai_rate_limit_window_seconds: int = Field(default=60, gt=0)

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "yolo_model_path",
        "upload_dir",
        "annotated_output_dir",
        mode="after",
    )
    @classmethod
    def resolve_project_path(cls, value: Path) -> Path:
        """Resolve configured relative paths consistently from the project root."""

        expanded_path = value.expanduser()
        if expanded_path.is_absolute():
            return expanded_path.resolve()
        return (PROJECT_ROOT / expanded_path).resolve()

    @field_validator("log_level", mode="after")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level.")
        return normalized

    @model_validator(mode="after")
    def validate_service_configuration(self) -> "Settings":
        parsed_ollama_url = urlparse(self.ollama_base_url)
        if (
            parsed_ollama_url.scheme not in {"http", "https"}
            or not parsed_ollama_url.hostname
        ):
            raise ValueError("OLLAMA_BASE_URL must be a valid HTTP or HTTPS URL.")

        hostname = parsed_ollama_url.hostname
        is_loopback = hostname == "localhost"
        if not is_loopback:
            try:
                is_loopback = ip_address(hostname).is_loopback
            except ValueError:
                is_loopback = False
        if not is_loopback and not self.ollama_allow_remote:
            raise ValueError(
                "Remote Ollama hosts require OLLAMA_ALLOW_REMOTE=true."
            )

        has_supabase_url = bool(self.supabase_url.strip())
        has_supabase_key = bool(self.supabase_publishable_key.strip())
        if has_supabase_url != has_supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured together."
            )
        if has_supabase_url:
            parsed_supabase_url = urlparse(self.supabase_url)
            if (
                parsed_supabase_url.scheme != "https"
                or not parsed_supabase_url.hostname
            ):
                raise ValueError("SUPABASE_URL must be a valid HTTPS URL.")
        return self

    @property
    def allowed_cors_origins(self) -> list[str]:
        """Return explicit browser origins; wildcard origins are not accepted."""

        origins = [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]
        if "*" in origins:
            raise ValueError("CORS_ALLOWED_ORIGINS cannot contain a wildcard.")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
