"""Run local YOLO detection followed by Ollama waste report generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.ai import (  # noqa: E402
    DEFAULT_CONFIDENCE_THRESHOLD,
    detect_waste,
    generate_waste_report,
)


DetectionFunction = Callable[[str | Path, float], Mapping[str, Any]]
ReportFunction = Callable[[Mapping[str, object]], Mapping[str, Any]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local YOLO detection and generate an Ollama waste report.",
    )
    parser.add_argument("image", type=Path, help="Path to the waste image")
    parser.add_argument(
        "--confidence",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help=f"YOLO confidence threshold (default: {DEFAULT_CONFIDENCE_THRESHOLD})",
    )
    return parser.parse_args(argv)


def _print_json(title: str, value: object) -> None:
    print(title)
    print(json.dumps(value, indent=2, sort_keys=True))


def run_pipeline(
    image_path: str | Path,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    *,
    detector: DetectionFunction = detect_waste,
    report_generator: ReportFunction = generate_waste_report,
) -> int:
    """Run detection first and call Ollama only for non-empty YOLO results."""
    detection_result = detector(image_path, confidence_threshold)
    _print_json("1. YOLO detection JSON", detection_result)

    counts = detection_result.get("counts", {})
    _print_json("2. Waste counts", counts)

    detections = detection_result.get("detections")
    total_objects = detection_result.get("total_objects")
    has_detections = (
        detection_result.get("success") is True
        and isinstance(total_objects, int)
        and not isinstance(total_objects, bool)
        and total_objects > 0
        and isinstance(detections, list)
        and bool(detections)
    )

    if not has_detections:
        if detection_result.get("code") == "NO_WASTE_DETECTED" or (
            detection_result.get("success") is True
            and (total_objects == 0 or detections == [])
        ):
            print("No YOLO detections. Ollama report generation was skipped.")
            return 0

        print("YOLO detection failed. Ollama report generation was skipped.", file=sys.stderr)
        return 2

    report = report_generator(detection_result)
    _print_json("3. Ollama-generated report JSON", report)

    if report.get("success") is False:
        return 3
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_pipeline(args.image, args.confidence)


if __name__ == "__main__":
    raise SystemExit(main())
