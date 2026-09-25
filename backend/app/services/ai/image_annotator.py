"""Save annotated copies of YOLO result images."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings


ANNOTATED_OUTPUT_DIR = get_settings().annotated_output_dir
BOX_COLORS = (
    "#007A5A",
    "#D95D39",
    "#3465A4",
    "#8E5EA2",
    "#A05A00",
)


class ImageAnnotationError(RuntimeError):
    """Raised when an annotated output image cannot be created."""


def _unique_output_path(output_dir: Path) -> Path:
    while True:
        candidate = output_dir / f"annotated-{uuid4().hex}.jpg"
        if not candidate.exists():
            return candidate


def _class_name(names: dict[int, str] | list[str], class_id: int) -> str:
    if isinstance(names, dict):
        return names.get(class_id, f"class_{class_id}")
    if 0 <= class_id < len(names):
        return names[class_id]
    return f"class_{class_id}"


def _draw_detections(image: Image.Image, result: Any) -> None:
    if result.boxes is None:
        return

    draw = ImageDraw.Draw(image)
    line_width = max(2, round(min(image.size) / 250))
    font_size = max(12, round(min(image.size) / 35))
    font = ImageFont.load_default(size=font_size)

    for box in result.boxes:
        class_id = int(box.cls.item())
        confidence = float(box.conf.item())
        x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        color = BOX_COLORS[class_id % len(BOX_COLORS)]
        label = f"{_class_name(result.names, class_id)} {confidence:.1%}"

        draw.rectangle((left, top, right, bottom), outline=color, width=line_width)

        text_left, text_top, text_right, text_bottom = draw.textbbox(
            (0, 0), label, font=font
        )
        text_width = text_right - text_left
        text_height = text_bottom - text_top
        padding = max(3, line_width)
        label_x = max(0, min(left, image.width - text_width - 2 * padding))
        label_y = max(0, top - text_height - 2 * padding)
        draw.rectangle(
            (
                label_x,
                label_y,
                label_x + text_width + 2 * padding,
                label_y + text_height + 2 * padding,
            ),
            fill=color,
        )
        draw.text(
            (label_x + padding, label_y + padding - text_top),
            label,
            fill="white",
            font=font,
        )


def save_annotated_image(
    result: Any,
    source_image_path: str | Path,
    output_dir: str | Path = ANNOTATED_OUTPUT_DIR,
) -> Path:
    """Save a uniquely named annotated copy without changing the source image."""

    resolved_source_path = Path(source_image_path).expanduser().resolve()
    resolved_output_dir = Path(output_dir).expanduser().resolve()
    output_path = _unique_output_path(resolved_output_dir)

    try:
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        with Image.open(resolved_source_path) as source_image:
            annotated_image = source_image.convert("RGB")
        _draw_detections(annotated_image, result)
        annotated_image.save(output_path, format="JPEG", quality=92)
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        raise ImageAnnotationError(
            f"Failed to create annotated image: {output_path}: {exc}"
        ) from exc

    if not output_path.is_file():
        raise ImageAnnotationError(
            f"Annotated image was not created: {output_path}"
        )

    return output_path
