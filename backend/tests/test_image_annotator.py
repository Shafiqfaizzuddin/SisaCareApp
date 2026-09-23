from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services.ai.image_annotator import (
    ImageAnnotationError,
    save_annotated_image,
)


class FakeValue:
    def __init__(self, value: float) -> None:
        self.value = value

    def item(self) -> float:
        return self.value


class FakeCoordinates:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def tolist(self) -> list[float]:
        return self.values


def fake_result() -> SimpleNamespace:
    return SimpleNamespace(
        names={0: "plastic_bottle"},
        boxes=[
            SimpleNamespace(
                cls=FakeValue(0),
                conf=FakeValue(0.91),
                xyxy=[FakeCoordinates([20.0, 30.0, 160.0, 150.0])],
            )
        ],
    )


def test_save_annotated_image_preserves_source_and_uses_unique_names(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.png"
    Image.new("RGB", (200, 180), "white").save(source_path)
    source_before = source_path.read_bytes()
    output_dir = tmp_path / "annotated"

    first_path = save_annotated_image(fake_result(), source_path, output_dir)
    second_path = save_annotated_image(fake_result(), source_path, output_dir)

    assert source_path.read_bytes() == source_before
    assert first_path != second_path
    assert first_path.parent == output_dir
    assert second_path.parent == output_dir
    assert first_path.suffix == ".jpg"
    assert second_path.suffix == ".jpg"

    with Image.open(first_path) as annotated_image:
        assert annotated_image.size == (200, 180)
        assert annotated_image.convert("RGB").getpixel((20, 30)) != (255, 255, 255)


def test_save_annotated_image_copies_image_without_detections(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    Image.new("RGB", (40, 30), "white").save(source_path)
    result = SimpleNamespace(names={}, boxes=None)

    output_path = save_annotated_image(result, source_path, tmp_path / "annotated")

    with Image.open(output_path) as annotated_image:
        assert annotated_image.size == (40, 30)


def test_save_annotated_image_removes_partial_output_on_failure(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "invalid.jpg"
    source_path.write_bytes(b"not an image")
    output_dir = tmp_path / "annotated"

    with pytest.raises(ImageAnnotationError, match="Failed to create"):
        save_annotated_image(fake_result(), source_path, output_dir)

    assert list(output_dir.iterdir()) == []
