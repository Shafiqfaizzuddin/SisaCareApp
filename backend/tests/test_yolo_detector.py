from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services.ai import yolo_detector


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


def fake_box(class_id: int, confidence: float, coordinates: list[float]) -> SimpleNamespace:
    return SimpleNamespace(
        cls=FakeValue(class_id),
        conf=FakeValue(confidence),
        xyxy=[FakeCoordinates(coordinates)],
    )


class FakeModel:
    def __init__(self, boxes: list[SimpleNamespace]) -> None:
        self.boxes = boxes
        self.predict_calls: list[dict[str, object]] = []

    def predict(self, **kwargs: object) -> list[SimpleNamespace]:
        self.predict_calls.append(kwargs)
        return [
            SimpleNamespace(
                names={0: "plastic_bottle", 1: "metal_can"},
                boxes=self.boxes,
            )
        ]


def create_valid_image(tmp_path: Path, name: str = "waste.jpg") -> Path:
    image_path = tmp_path / name
    Image.new("RGB", (200, 160), "white").save(image_path)
    return image_path


def assert_failure_has_no_detection_data(result: object) -> None:
    assert isinstance(result, dict)
    assert "detections" not in result
    assert "counts" not in result
    assert "annotated_image_path" not in result


def test_valid_image_with_waste_returns_enriched_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    annotated_path = tmp_path / "annotated.jpg"
    model = FakeModel(
        [
            fake_box(0, 0.91, [10.0, 20.0, 110.0, 120.0]),
            fake_box(0, 0.82, [15.0, 25.0, 90.0, 100.0]),
            fake_box(1, 0.77, [120.0, 50.0, 180.0, 140.0]),
        ]
    )
    monkeypatch.setattr(yolo_detector, "_load_model", lambda: model)
    monkeypatch.setattr(
        yolo_detector,
        "save_annotated_image",
        lambda _result, _source_path: annotated_path,
    )

    result = yolo_detector.detect_waste(image_path, confidence_threshold=0.55)

    assert result["success"] is True
    assert result["code"] == "WASTE_DETECTED"
    assert result["message"] == "Supported waste objects were detected successfully."
    assert result["total_objects"] == 3
    assert result["counts"] == {"plastic_bottle": 2, "metal_can": 1}
    assert result["annotated_image_path"] == str(annotated_path)
    assert result["detections"][0] == {
        "class_name": "plastic_bottle",
        "class_id": 0,
        "confidence": 0.91,
        "display_name": "Plastic Bottle",
        "waste_category": "Recyclable Waste",
        "material": "Plastic",
        "recyclable": True,
        "recommended_handling": (
            "Empty, rinse, and place in an appropriate plastic recycling stream."
        ),
        "bounding_box": {
            "x1": 10.0,
            "y1": 20.0,
            "x2": 110.0,
            "y2": 120.0,
        },
    }
    assert model.predict_calls == [
        {
            "source": str(image_path.resolve()),
            "conf": 0.55,
            "verbose": False,
        }
    ]


def test_valid_image_without_waste_returns_no_detection_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    monkeypatch.setattr(yolo_detector, "_load_model", lambda: FakeModel([]))
    monkeypatch.setattr(
        yolo_detector,
        "save_annotated_image",
        lambda *_args: pytest.fail("No-detection result must not be annotated."),
    )

    result = yolo_detector.detect_waste(image_path)

    assert result == {
        "success": False,
        "code": "NO_WASTE_DETECTED",
        "message": "No supported waste objects were detected in this image.",
    }
    assert_failure_has_no_detection_data(result)


def test_corrupted_image_returns_consistent_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "corrupted.jpg"
    image_path.write_bytes(b"not an image")
    monkeypatch.setattr(
        yolo_detector,
        "_load_model",
        lambda: pytest.fail("Invalid images must be rejected before model loading."),
    )

    result = yolo_detector.detect_waste(image_path)

    assert result == {
        "success": False,
        "code": "INVALID_IMAGE",
        "message": "The uploaded image is invalid or corrupted.",
    }
    assert_failure_has_no_detection_data(result)


def test_unsupported_file_type_returns_consistent_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path, "waste.gif")
    monkeypatch.setattr(
        yolo_detector,
        "_load_model",
        lambda: pytest.fail("Unsupported files must be rejected before model loading."),
    )

    result = yolo_detector.detect_waste(image_path)

    assert result == {
        "success": False,
        "code": "UNSUPPORTED_FILE_TYPE",
        "message": "Unsupported file type. Supported types are JPEG, PNG, and WEBP.",
    }
    assert_failure_has_no_detection_data(result)


def test_model_inference_error_returns_consistent_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    model = SimpleNamespace(
        predict=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("GPU failure"))
    )
    monkeypatch.setattr(yolo_detector, "_load_model", lambda: model)

    result = yolo_detector.detect_waste(image_path)

    assert result == {
        "success": False,
        "code": "MODEL_INFERENCE_ERROR",
        "message": "The waste detection model could not process this image.",
    }
    assert_failure_has_no_detection_data(result)


def test_missing_model_returns_consistent_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)

    def missing_model() -> object:
        raise yolo_detector.ModelNotFoundError("missing model")

    monkeypatch.setattr(yolo_detector, "_load_model", missing_model)

    result = yolo_detector.detect_waste(image_path)

    assert result == {
        "success": False,
        "code": "MODEL_NOT_FOUND",
        "message": "The waste detection model file is missing.",
    }
    assert_failure_has_no_detection_data(result)


def test_missing_image_returns_consistent_failure() -> None:
    result = yolo_detector.detect_waste("missing-image.jpg")

    assert result == {
        "success": False,
        "code": "IMAGE_NOT_FOUND",
        "message": "The image file does not exist.",
    }
    assert_failure_has_no_detection_data(result)


@pytest.mark.parametrize("threshold", [-0.01, 1.01, True, "0.5"])
def test_invalid_confidence_returns_consistent_failure(threshold: object) -> None:
    result = yolo_detector.detect_waste(
        "unused.jpg",
        threshold,  # type: ignore[arg-type]
    )

    assert result == {
        "success": False,
        "code": "INVALID_CONFIDENCE_THRESHOLD",
        "message": "Confidence threshold must be a number between 0 and 1.",
    }
    assert_failure_has_no_detection_data(result)


def test_annotation_error_returns_consistent_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    monkeypatch.setattr(
        yolo_detector,
        "_load_model",
        lambda: FakeModel([fake_box(0, 0.91, [10.0, 20.0, 110.0, 120.0])]),
    )

    def fail_annotation(_result: object, _source_path: Path) -> Path:
        raise yolo_detector.ImageAnnotationError("render failed")

    monkeypatch.setattr(yolo_detector, "save_annotated_image", fail_annotation)

    result = yolo_detector.detect_waste(image_path)

    assert result == {
        "success": False,
        "code": "ANNOTATION_ERROR",
        "message": "The annotated image could not be created.",
    }
    assert_failure_has_no_detection_data(result)


def test_default_confidence_is_forwarded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    model = FakeModel([])
    monkeypatch.setattr(yolo_detector, "_load_model", lambda: model)

    yolo_detector.detect_waste(image_path)

    assert model.predict_calls[0]["conf"] == 0.35
