"""Shared image upload storage rules for API endpoints."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings


MAX_UPLOAD_SIZE = get_settings().max_upload_size
UPLOAD_CHUNK_SIZE = 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_EXTENSIONS_BY_TYPE = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}


class UploadMetadataError(ValueError):
    """Raised when client-provided upload metadata is unsafe or inconsistent."""


def validate_image_upload_metadata(
    filename: str | None,
    content_type: str | None,
) -> str:
    """Validate the declared MIME type and filename without trusting either."""

    normalized_type = (content_type or "").lower().strip()
    canonical_extension = ALLOWED_IMAGE_TYPES.get(normalized_type)
    if canonical_extension is None:
        raise UploadMetadataError("UNSUPPORTED_FILE_TYPE")

    if (
        not filename
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
        or Path(filename).name != filename
    ):
        raise UploadMetadataError("INVALID_FILENAME")

    supplied_extension = Path(filename).suffix.lower()
    if supplied_extension not in ALLOWED_EXTENSIONS_BY_TYPE[normalized_type]:
        raise UploadMetadataError("FILE_TYPE_MISMATCH")
    return canonical_extension


def create_unique_upload_path(
    upload_dir: str | Path,
    *,
    prefix: str,
    extension: str,
) -> Path:
    """Create a traversal-safe server filename under the configured directory."""

    if extension not in set(ALLOWED_IMAGE_TYPES.values()):
        raise ValueError("Unsupported server-side image extension.")
    if not prefix.isascii() or not prefix.replace("-", "").isalnum():
        raise ValueError("Invalid upload filename prefix.")

    resolved_root = Path(upload_dir).expanduser().resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    candidate = (resolved_root / f"{prefix}-{uuid4().hex}{extension}").resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Upload path escaped the configured directory.") from exc
    return candidate


def upload_size_limit_message(max_size: int = MAX_UPLOAD_SIZE) -> str:
    """Return a readable upload-size validation message for the active limit."""

    mebibyte = 1024 * 1024
    if max_size % mebibyte == 0:
        limit = f"{max_size // mebibyte} MB"
    else:
        limit = f"{max_size} bytes"
    return f"The image must be {limit} or smaller."


async def save_image_upload(
    image: UploadFile,
    destination: Path,
    *,
    max_size: int = MAX_UPLOAD_SIZE,
    chunk_size: int = UPLOAD_CHUNK_SIZE,
) -> None:
    total_size = 0
    destination_created = False
    try:
        with destination.open("xb") as output:
            destination_created = True
            while chunk := await image.read(chunk_size):
                total_size += len(chunk)
                if total_size > max_size:
                    raise ValueError("IMAGE_TOO_LARGE")
                output.write(chunk)
    except Exception:
        if destination_created:
            destination.unlink(missing_ok=True)
        raise
    finally:
        await image.close()

    if total_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("EMPTY_IMAGE")


__all__ = [
    "ALLOWED_EXTENSIONS_BY_TYPE",
    "ALLOWED_IMAGE_TYPES",
    "MAX_UPLOAD_SIZE",
    "UPLOAD_CHUNK_SIZE",
    "UploadMetadataError",
    "create_unique_upload_path",
    "save_image_upload",
    "upload_size_limit_message",
    "validate_image_upload_metadata",
]
