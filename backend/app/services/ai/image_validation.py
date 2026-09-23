"""Validate image inputs before YOLO inference."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


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
        raise ImageNotFoundError(f"Image not found: {resolved_image_path}")

    if resolved_image_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported image extension: {resolved_image_path.suffix or '<none>'}"
        )

    try:
        with Image.open(resolved_image_path) as image:
            detected_format = image.format
            image.verify()
    except (OSError, SyntaxError, UnidentifiedImageError) as exc:
        raise InvalidImageError(f"Invalid or corrupted image: {resolved_image_path}") from exc

    if detected_format not in SUPPORTED_FORMATS:
        raise UnsupportedFileTypeError(
            f"Unsupported decoded image format: {detected_format or 'unknown'}"
        )

    return resolved_image_path
