"""Run the reusable waste detector against one local image."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.ai import (  # noqa: E402
    DEFAULT_CONFIDENCE_THRESHOLD,
    detect_waste,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run YOLO waste detection on a local image.",
    )
    parser.add_argument("image", type=Path, help="Path to the image to process")
    parser.add_argument(
        "--confidence",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help=f"Confidence threshold from 0 to 1 (default: {DEFAULT_CONFIDENCE_THRESHOLD})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    result = detect_waste(args.image, args.confidence)
    if not result["success"]:
        stream = sys.stdout if result["code"] == "NO_WASTE_DETECTED" else sys.stderr
        print(f"{result['code']}: {result['message']}", file=stream)
        return 0 if result["code"] == "NO_WASTE_DETECTED" else 2

    for index, detection in enumerate(result["detections"], start=1):
        box = detection["bounding_box"]
        print(f"Detection {index}")
        print(f"  Class: {detection['class_name']}")
        print(f"  Class ID: {detection['class_id']}")
        print(f"  Confidence: {detection['confidence']:.4f}")
        print(f"  Display name: {detection['display_name']}")
        print(f"  Waste category: {detection['waste_category']}")
        print(f"  Material: {detection['material']}")
        print(f"  Recyclable: {detection['recyclable']}")
        print(f"  Recommended handling: {detection['recommended_handling']}")
        print(
            "  Bounding box (x1, y1, x2, y2): "
            f"({box['x1']:.2f}, {box['y1']:.2f}, "
            f"{box['x2']:.2f}, {box['y2']:.2f})"
        )

    if result["total_objects"] == 0:
        print("No objects detected.")

    print(f"Counts by class: {result['counts']}")
    print(f"Total detected objects: {result['total_objects']}")
    print(f"Annotated image: {result['annotated_image_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
