from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services.ai import image_validation


def test_decoded_format_must_match_extension(tmp_path: Path) -> None:
    image_path = tmp_path / "mismatch.jpg"
    Image.new("RGB", (2, 2), "white").save(image_path, format="PNG")

    with pytest.raises(image_validation.UnsupportedFileTypeError):
        image_validation.validate_image(image_path)


def test_decoded_pixel_limit_blocks_decompression_pressure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "large.png"
    Image.new("RGB", (3, 3), "white").save(image_path)
    monkeypatch.setattr(
        image_validation,
        "get_settings",
        lambda: SimpleNamespace(max_image_pixels=4),
    )

    with pytest.raises(image_validation.InvalidImageError):
        image_validation.validate_image(image_path)
