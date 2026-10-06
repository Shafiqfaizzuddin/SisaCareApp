"""Run the trained YOLO detector without VLM, reports, or persistence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.ai import yolo_detector  # noqa: E402


DEFAULT_CONFIDENCE_THRESHOLD = yolo_detector.DEFAULT_CONFIDENCE_THRESHOLD
detect_waste = yolo_detector.detect_waste


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run YOLO waste detection on a local image.",
    )
    parser.add_argument(
        "image",
        nargs="?",
        type=Path,
        help="Path to one image to inspect",
    )
    parser.add_argument(
        "--valid-image",
        type=Path,
        help="Suite image expected to contain at least one supported object",
    )
    parser.add_argument(
        "--several-objects-image",
        type=Path,
        help="Suite image expected to contain at least two supported objects",
    )
    parser.add_argument(
        "--no-supported-object-image",
        type=Path,
        help="Suite image expected to contain no supported object",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help=f"Confidence threshold from 0 to 1 (default: {DEFAULT_CONFIDENCE_THRESHOLD})",
    )
    args = parser.parse_args(argv)
    suite_images = (
        args.valid_image,
        args.several_objects_image,
        args.no_supported_object_image,
    )
    if args.image is not None and any(suite_images):
        parser.error("Use either one positional image or the three suite options.")
    if any(suite_images) and not all(suite_images):
        parser.error("All three suite image options must be supplied together.")
    if args.image is None and not any(suite_images):
        parser.error("Provide one image or all three suite image options.")
    return args


def print_result(label: str, result: object) -> None:
    assert isinstance(result, dict)
    print(f"\n=== {label} ===")
    if not result["success"]:
        print(f"{result['code']}: {result['message']}")
        print("Raw detections: []")
        print("Total detected objects: 0")
        return

    print("Raw detections:")
    print(json.dumps(result["detections"], indent=2, sort_keys=True))
    for index, detection in enumerate(result["detections"], start=1):
        box = detection["bounding_box"]
        print(f"Detection {index}")
        print(f"  Class: {detection['class_name']}")
        print(f"  Class ID: {detection['class_id']}")
        print(f"  Confidence: {detection['confidence']:.4f}")
        print(f"  Source: {detection['source']}")
        print(
            "  Bounding box (x1, y1, x2, y2): "
            f"({box['x1']:.2f}, {box['y1']:.2f}, "
            f"{box['x2']:.2f}, {box['y2']:.2f})"
        )
    print(f"Counts by class: {result['counts']}")
    print(f"Total detected objects: {result['total_objects']}")
    print(f"Annotated image: {result['annotated_image_path']}")


def run_case(label: str, image: Path, confidence: float) -> dict[str, object]:
    result = detect_waste(image, confidence)
    print_result(label, result)
    return result


def run_suite(args: argparse.Namespace) -> int:
    with TemporaryDirectory(prefix="sisacare-yolo-test-") as temp_directory:
        temp_path = Path(temp_directory)
        invalid_image = temp_path / "invalid-image.jpg"
        invalid_image.write_bytes(b"this is not image data")

        valid = run_case("1. Valid waste image", args.valid_image, args.confidence)
        several = run_case(
            "2. Several supported objects",
            args.several_objects_image,
            args.confidence,
        )
        no_supported = run_case(
            "3. No supported object",
            args.no_supported_object_image,
            args.confidence,
        )
        invalid = run_case("4. Invalid image", invalid_image, args.confidence)

        original_model_path = yolo_detector.MODEL_PATH
        original_model = yolo_detector._model
        try:
            yolo_detector.MODEL_PATH = temp_path / "missing-model.pt"
            yolo_detector._model = None
            missing_model = run_case(
                "5. Missing model",
                args.valid_image,
                args.confidence,
            )
        finally:
            yolo_detector.MODEL_PATH = original_model_path
            yolo_detector._model = original_model

    passed = (
        valid.get("success") is True
        and int(valid.get("total_objects", 0)) >= 1
        and several.get("success") is True
        and int(several.get("total_objects", 0)) >= 2
        and no_supported.get("code") == "NO_WASTE_DETECTED"
        and invalid.get("code") == "INVALID_IMAGE"
        and missing_model.get("code") == "MODEL_NOT_FOUND"
    )
    print(f"\nYOLO local suite: {'PASSED' if passed else 'FAILED'}")
    return 0 if passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.image is None:
        return run_suite(args)

    result = detect_waste(args.image, args.confidence)
    if not result["success"]:
        stream = sys.stdout if result["code"] == "NO_WASTE_DETECTED" else sys.stderr
        print(f"{result['code']}: {result['message']}", file=stream)
        print("Raw detections: []", file=stream)
        print("Total detected objects: 0", file=stream)
        return 0 if result["code"] == "NO_WASTE_DETECTED" else 2

    print_result("YOLO detection", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
