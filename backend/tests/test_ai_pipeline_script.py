from pathlib import Path
from runpy import run_path
from typing import Any, Mapping


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "ai" / "test_ai_pipeline.py"
SCRIPT = run_path(str(SCRIPT_PATH))
run_pipeline = SCRIPT["run_pipeline"]


def successful_detection() -> dict[str, Any]:
    return {
        "success": True,
        "code": "WASTE_DETECTED",
        "message": "Supported waste objects were detected successfully.",
        "total_objects": 1,
        "counts": {"plastic_bottle": 1},
        "detections": [
            {
                "class_name": "plastic_bottle",
                "class_id": 0,
                "confidence": 0.91,
                "display_name": "Plastic Bottle",
                "waste_category": "Recyclable Waste",
                "material": "Plastic",
                "recyclable": True,
                "recommended_handling": "Recycle appropriately.",
                "bounding_box": {"x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0},
            }
        ],
        "annotated_image_path": "annotated.jpg",
    }


def test_successful_pipeline_prints_detection_counts_and_report(capsys: Any) -> None:
    detection_result = successful_detection()
    received_detection: Mapping[str, object] | None = None

    def detector(_path: str | Path, confidence: float) -> Mapping[str, Any]:
        assert confidence == 0.4
        return detection_result

    def report_generator(
        detection: Mapping[str, object],
    ) -> Mapping[str, Any]:
        nonlocal received_detection
        received_detection = detection
        return {
            "title": "Municipal Waste Report",
            "summary": "One recyclable item was detected.",
            "waste_identified": "One plastic bottle.",
            "recommended_action": "Place it in the plastic recycling stream.",
            "environmental_concern": "Improper disposal may contribute to litter.",
        }

    exit_code = run_pipeline(
        "waste.jpg",
        0.4,
        detector=detector,
        report_generator=report_generator,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert received_detection is detection_result
    assert "1. YOLO detection JSON" in output
    assert "2. Waste counts" in output
    assert '"plastic_bottle": 1' in output
    assert "3. Ollama-generated report JSON" in output
    assert '"title": "Municipal Waste Report"' in output


def test_no_detection_never_calls_ollama(capsys: Any) -> None:
    def detector(_path: str | Path, _confidence: float) -> Mapping[str, Any]:
        return {
            "success": False,
            "code": "NO_WASTE_DETECTED",
            "message": "No supported waste objects were detected in this image.",
        }

    def report_generator(_detection: Mapping[str, object]) -> Mapping[str, Any]:
        raise AssertionError("Ollama must not be called without YOLO detections.")

    exit_code = run_pipeline(
        "empty.jpg",
        detector=detector,
        report_generator=report_generator,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "2. Waste counts\n{}" in output
    assert "Ollama report generation was skipped" in output
    assert "3. Ollama-generated report JSON" not in output


def test_inconsistent_zero_count_never_calls_ollama(capsys: Any) -> None:
    detection_result = successful_detection()
    detection_result["total_objects"] = 0
    detection_result["counts"] = {}
    detection_result["detections"] = []

    def detector(_path: str | Path, _confidence: float) -> Mapping[str, Any]:
        return detection_result

    def report_generator(_detection: Mapping[str, object]) -> Mapping[str, Any]:
        raise AssertionError("Ollama must not be called for zero objects.")

    exit_code = run_pipeline(
        "empty.jpg",
        detector=detector,
        report_generator=report_generator,
    )

    assert exit_code == 0
    assert "Ollama report generation was skipped" in capsys.readouterr().out


def test_detection_error_never_calls_ollama(capsys: Any) -> None:
    def detector(_path: str | Path, _confidence: float) -> Mapping[str, Any]:
        return {
            "success": False,
            "code": "INVALID_IMAGE",
            "message": "The uploaded image is invalid or corrupted.",
        }

    def report_generator(_detection: Mapping[str, object]) -> Mapping[str, Any]:
        raise AssertionError("Ollama must not be called after detection failure.")

    exit_code = run_pipeline(
        "broken.jpg",
        detector=detector,
        report_generator=report_generator,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Ollama report generation was skipped" in captured.err
    assert "3. Ollama-generated report JSON" not in captured.out
