"""Server-only access to the private Supabase report image bucket."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import get_settings


BUCKET = "sisacare-private"
EDUCATION_BUCKET = "sisacare-education"
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _object_url(object_key: str, bucket: str = BUCKET, *, authenticated: bool = False) -> str:
    if bucket not in {BUCKET, EDUCATION_BUCKET}:
        raise ValueError("Unknown Storage bucket.")
    settings = get_settings()
    route = "object/authenticated" if authenticated else "object"
    return f"{settings.supabase_url.rstrip('/')}/storage/v1/{route}/{bucket}/{quote(object_key, safe='/')}"


def _headers() -> dict[str, str]:
    key = get_settings().supabase_service_role_key.get_secret_value()
    if not key:
        raise RuntimeError("Server-only Supabase Storage credential is missing.")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def put_file(object_key: str, source: Path, *, bucket: str = BUCKET) -> tuple[str, str, int]:
    """Upload once, with an immutable key; return MIME, SHA-256, and size."""
    if not source.is_file() or source.suffix.lower() not in MEDIA_TYPES:
        raise ValueError("A valid image source is required.")
    data = source.read_bytes()
    if not data or len(data) > get_settings().max_upload_size:
        raise ValueError("Image exceeds the configured storage limit.")
    content_type = MEDIA_TYPES[source.suffix.lower()]
    with httpx.Client(timeout=30) as client:
        response = client.post(
            _object_url(object_key, bucket),
            headers={**_headers(), "x-upsert": "false"},
            files={"file": (source.name, data, content_type)},
        )
    response.raise_for_status()
    return content_type, hashlib.sha256(data).hexdigest(), len(data)


def get_file(object_key: str, *, bucket: str = BUCKET) -> bytes:
    with httpx.Client(timeout=30) as client:
        response = client.get(_object_url(object_key, bucket, authenticated=True), headers=_headers())
    response.raise_for_status()
    return response.content


def delete_file(object_key: str, *, bucket: str = BUCKET) -> None:
    with httpx.Client(timeout=30) as client:
        response = client.delete(_object_url(object_key, bucket), headers=_headers())
    if response.status_code not in {200, 204, 404}:
        response.raise_for_status()
