"""Read deployment configuration independently of the application backend."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("config.json")
OFFICIAL_MODELS = {
    "microsoft/Florence-2-base",
    "microsoft/Florence-2-large",
}


@dataclass(frozen=True)
class Settings:
    model_id: str
    model_revision: str
    device_preference: str
    host: str
    port: int
    max_upload_bytes: int
    max_image_pixels: int
    max_image_side: int
    max_new_tokens: int
    num_beams: int
    queue_timeout_seconds: float


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Florence configuration must be a JSON object.")
    values = {
        key: os.getenv(f"FLORENCE_{key.upper()}", value)
        for key, value in raw.items()
    }
    model_id = str(values["model_id"])
    revision = str(values["model_revision"])
    if model_id not in OFFICIAL_MODELS:
        raise ValueError("Only the official Microsoft base and large checkpoints are allowed.")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("model_revision must be a pinned 40-character commit hash.")
    device_preference = str(values["device_preference"])
    if device_preference not in {"auto", "cuda", "cpu"}:
        raise ValueError("device_preference must be auto, cuda, or cpu.")
    host = str(values["host"])
    try:
        is_loopback = ip_address(host).is_loopback
    except ValueError:
        is_loopback = host == "localhost"
    if not is_loopback:
        raise ValueError("Florence service must bind to a loopback address.")
    settings = Settings(
        model_id=model_id,
        model_revision=revision,
        device_preference=device_preference,
        host=host,
        port=int(values["port"]),
        max_upload_bytes=int(values["max_upload_bytes"]),
        max_image_pixels=int(values["max_image_pixels"]),
        max_image_side=int(values["max_image_side"]),
        max_new_tokens=int(values["max_new_tokens"]),
        num_beams=int(values["num_beams"]),
        queue_timeout_seconds=float(values["queue_timeout_seconds"]),
    )
    if not 1 <= settings.port <= 65535:
        raise ValueError("port must be between 1 and 65535.")
    if not 1 <= settings.max_upload_bytes <= 50 * 1024 * 1024:
        raise ValueError("max_upload_bytes must be between 1 and 50 MiB.")
    if not 1 <= settings.max_image_pixels <= 100_000_000:
        raise ValueError("max_image_pixels must be between 1 and 100 million.")
    if not 1 <= settings.max_image_side <= 20_000:
        raise ValueError("max_image_side must be between 1 and 20,000.")
    if not 1 <= settings.max_new_tokens <= 1024:
        raise ValueError("max_new_tokens must be between 1 and 1024.")
    if not 1 <= settings.num_beams <= 5:
        raise ValueError("num_beams must be between 1 and 5.")
    if not 0 < settings.queue_timeout_seconds <= 30:
        raise ValueError("queue_timeout_seconds must be between 0 and 30.")
    return settings
