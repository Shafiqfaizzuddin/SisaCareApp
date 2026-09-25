"""Validate image inputs before YOLO inference."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings


logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
FORMAT_EXTENSIONS = {
    "JPEG": {".jpg", ".jpeg"},
    "PNG": {".png"},
    "WEBP": {".webp"},
}


class ImageValidationError(ValueError):
    """Base exception for invalid image inputs."""

    code = "INVALID_IMAGE"
    public_message = "The uploaded image is invalid or corrupted."


class ImageNotFoundError(ImageValidationError):
    """Raised when an input image does not exist."""

    code = "IMAGE_NOT_FOUND"
    public_message = "The image file does not exist."


class UnsupportedFileTypeError(ImageValidationError):
    """Raised when an image type is not supported."""

    code = "UNSUPPORTED_FILE_TYPE"
    public_message = "Unsupported file type. Supported types are JPEG, PNG, and WEBP."


class InvalidImageError(ImageValidationError):
    """Raised when an image is unreadable or corrupted."""


def validate_image(image_path: str | Path) -> Path:
    """Validate the file path, extension, and decoded image content."""

    resolved_image_path = Path(image_path).expanduser().resolve()
    if not resolved_image_path.is_file():
        logger.warning("image_validation_failed code=IMAGE_NOT_FOUND")
        raise ImageNotFoundError(f"Image not found: {resolved_image_path}")

    if resolved_image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        logger.warning("image_validation_failed code=UNSUPPORTED_FILE_TYPE")
        raise UnsupportedFileTypeError(
            f"Unsupported image extension: {resolved_image_path.suffix or '<none>'}"
        )

    try:
        with Image.open(resolved_image_path) as image:
            detected_format = image.format
            width, height = image.size
            if width <= 0 or height <= 0:
                raise InvalidImageError("Image dimensions must be positive.")
            if width * height > get_settings().max_image_pixels:
                raise InvalidImageError("Decoded image dimensions exceed the limit.")
            image.verify()
        with Image.open(resolved_image_path) as image:
            image.load()
    except InvalidImageError:
        logger.warning("image_validation_failed code=INVALID_IMAGE")
        raise
    except (
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as exc:
        logger.warning(
            "image_validation_failed code=INVALID_IMAGE error_type=%s",
            type(exc).__name__,
        )
        raise InvalidImageError(
            f"Invalid or corrupted image: {resolved_image_path}"
        ) from exc

    if detected_format not in SUPPORTED_FORMATS:
        logger.warning("image_validation_failed code=UNSUPPORTED_FILE_TYPE")
        raise UnsupportedFileTypeError(
            f"Unsupported decoded image format: {detected_format or 'unknown'}"
        )
    if resolved_image_path.suffix.lower() not in FORMAT_EXTENSIONS[detected_format]:
        logger.warning("image_validation_failed code=FILE_TYPE_MISMATCH")
        raise UnsupportedFileTypeError(
            "The decoded image format does not match its file extension."
        )

    logger.info(
        "image_validation_completed status=valid format=%s width=%d height=%d",
        detected_format,
        width,
        height,
    )
    return resolved_image_path
