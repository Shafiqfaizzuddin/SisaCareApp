"""Run standalone Ollama VLM waste analysis without YOLO or report generation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = PROJECT_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.services.ai.vlm_analyzer import analyze_waste_image_with_vlm  # noqa: E402


Analyzer = Callable[[str | Path], Mapping[str, Any]]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run standalone Ollama vision analysis on one local image or a "
            "six-image waste scenario suite."
        ),
    )
    parser.add_argument(
        "image",
        nargs="?",
        type=Path,
        help="One local image to analyze and print",
    )
    parser.add_argument("--recyclable-image", type=Path)
    parser.add_argument("--non-recyclable-image", type=Path)
    parser.add_argument("--bulky-image", type=Path)
    parser.add_argument("--mixed-image", type=Path)
    parser.add_argument("--unclear-image", type=Path)
    parser.add_argument("--no-waste-image", type=Path)
    args = parser.parse_args(argv)

    suite_images = (
        args.recyclable_image,
        args.non_recyclable_image,
        args.bulky_image,
        args.mixed_image,
        args.unclear_image,
        args.no_waste_image,
    )
    if args.image is not None and any(suite_images):
        parser.error("Use either one positional image or all six suite options.")
    if any(suite_images) and not all(suite_images):
        parser.error("All six suite image options must be supplied together.")
    if args.image is None and not any(suite_images):
        parser.error("Provide one image or all six suite image options.")
    return args


def is_failure(result: Mapping[str, Any]) -> bool:
    return result.get("success") is False


def print_raw_result(label: str, result: Mapping[str, Any]) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


def run_case(
    label: str,
    image_path: str | Path,
    *,
    analyzer: Analyzer = analyze_waste_image_with_vlm,
) -> Mapping[str, Any]:
    result = analyzer(image_path)
    print_raw_result(label, result)
    return result


def _objects(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    objects = result.get("objects")
    if not isinstance(objects, list):
        return []
    return [item for item in objects if isinstance(item, Mapping)]


def _has_category(result: Mapping[str, Any], category: str) -> bool:
    return any(item.get("suggested_category") == category for item in _objects(result))


def validate_suite_results(
    results: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for label, result in results.items():
        if is_failure(result):
            errors.append(f"{label} returned {result.get('code', 'an unknown error')}.")

    if not is_failure(results["recyclable"]) and not _has_category(
        results["recyclable"],
        "Recyclable Waste",
    ):
        errors.append("Recyclable image did not produce Recyclable Waste.")
    if not is_failure(results["non_recyclable"]) and not _has_category(
        results["non_recyclable"],
        "Non-Recyclable",
    ):
        errors.append("Non-recyclable image did not produce Non-Recyclable.")
    if not is_failure(results["bulky"]) and not _has_category(
        results["bulky"],
        "Bulky Waste",
    ):
        errors.append("Bulky image did not produce Bulky Waste.")

    if not is_failure(results["mixed"]):
        mixed_objects = _objects(results["mixed"])
        mixed_names = {str(item.get("name", "")).casefold() for item in mixed_objects}
        mixed_categories = {
            item.get("suggested_category")
            for item in mixed_objects
            if item.get("suggested_category") != "Unknown"
        }
        if len(mixed_names) < 2 or len(mixed_categories) < 2:
            errors.append(
                "Mixed image did not produce at least two object names across "
                "two known categories."
            )

    if not is_failure(results["no_waste"]) and _objects(results["no_waste"]):
        errors.append("No-waste image produced one or more waste objects.")
    return errors


def run_suite(
    images: Mapping[str, Path],
    *,
    analyzer: Analyzer = analyze_waste_image_with_vlm,
) -> int:
    cases = (
        ("recyclable", "1. Recyclable items"),
        ("non_recyclable", "2. Non-recyclable items"),
        ("bulky", "3. Bulky waste"),
        ("mixed", "4. Mixed waste"),
        ("unclear", "5. Difficult or unclear image"),
        ("no_waste", "6. No obvious waste"),
    )
    results = {
        key: run_case(label, images[key], analyzer=analyzer)
        for key, label in cases
    }
    errors = validate_suite_results(results)
    if errors:
        print("\nVLM local suite: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nVLM local suite: PASSED")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.image is not None:
        result = run_case("VLM waste analysis", args.image)
        return 2 if is_failure(result) else 0

    return run_suite(
        {
            "recyclable": args.recyclable_image,
            "non_recyclable": args.non_recyclable_image,
            "bulky": args.bulky_image,
            "mixed": args.mixed_image,
            "unclear": args.unclear_image,
            "no_waste": args.no_waste_image,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
