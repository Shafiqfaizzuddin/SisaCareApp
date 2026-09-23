"""Shared image upload storage rules for API endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile


MAX_UPLOAD_SIZE = 10 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def save_image_upload(
    image: UploadFile,
    destination: Path,
    *,
    max_size: int = MAX_UPLOAD_SIZE,
    chunk_size: int = UPLOAD_CHUNK_SIZE,
) -> None:
    total_size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await image.read(chunk_size):
                total_size += len(chunk)
                if total_size > max_size:
                    raise ValueError("IMAGE_TOO_LARGE")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await image.close()

    if total_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("EMPTY_IMAGE")


__all__ = [
    "ALLOWED_IMAGE_TYPES",
    "MAX_UPLOAD_SIZE",
    "UPLOAD_CHUNK_SIZE",
    "save_image_upload",
]

