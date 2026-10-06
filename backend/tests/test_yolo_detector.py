import logging
import sys
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
    def __init__(
        self,
        boxes: list[SimpleNamespace],
        names: dict[int, str] | None = None,
    ) -> None:
        self.boxes = boxes
        self.names = names or {0: "plastic_bottle", 1: "metal_can"}
        self.predict_calls: list[dict[str, object]] = []

    def predict(self, **kwargs: object) -> list[SimpleNamespace]:
        self.predict_calls.append(kwargs)
        return [
            SimpleNamespace(
                names=self.names,
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


def test_model_is_loaded_once_and_reused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"model")
    loaded_model = object()
    load_calls: list[str] = []

    def fake_yolo(path: str) -> object:
        load_calls.append(path)
        return loaded_model

    monkeypatch.setattr(yolo_detector, "MODEL_PATH", model_path)
    monkeypatch.setattr(yolo_detector, "_model", None)
    monkeypatch.setitem(
        sys.modules,
        "ultralytics",
        SimpleNamespace(YOLO=fake_yolo),
    )

    assert yolo_detector._load_model() is loaded_model
    assert yolo_detector._load_model() is loaded_model
    assert load_calls == [str(model_path)]


def test_valid_image_with_several_objects_returns_individual_detections(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.INFO)
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
        "bounding_box": {
            "x1": 10.0,
            "y1": 20.0,
            "x2": 110.0,
            "y2": 120.0,
        },
        "source": "yolo",
    }
    assert model.predict_calls == [
        {
            "source": str(image_path.resolve()),
            "conf": 0.55,
            "verbose": False,
        }
    ]
    assert "yolo_inference_completed" in caplog.text
    assert "detection_count=3" in caplog.text
    assert str(image_path) not in caplog.text


def test_valid_image_with_one_object_returns_structured_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    annotated_path = tmp_path / "annotated.jpg"
    model = FakeModel(
        [fake_box(0, 0.91, [10.0, 20.0, 110.0, 120.0])],
    )
    monkeypatch.setattr(yolo_detector, "_load_model", lambda: model)
    monkeypatch.setattr(
        yolo_detector,
        "save_annotated_image",
        lambda _result, _source_path: annotated_path,
    )

    result = yolo_detector.detect_waste(image_path)

    assert result["success"] is True
    assert result["total_objects"] == 1
    assert result["counts"] == {"plastic_bottle": 1}
    assert len(result["detections"]) == 1
    assert result["detections"][0]["source"] == "yolo"


def test_valid_image_without_waste_returns_structured_empty_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    annotated_path = tmp_path / "annotated.jpg"
    monkeypatch.setattr(yolo_detector, "_load_model", lambda: FakeModel([]))
    monkeypatch.setattr(
        yolo_detector,
        "save_annotated_image",
        lambda _result, _source_path: annotated_path,
    )

    result = yolo_detector.detect_waste(image_path)

    assert result == {
        "success": True,
        "code": "NO_WASTE_DETECTED",
        "message": "No supported waste objects were detected in this image.",
        "total_objects": 0,
        "counts": {},
        "detections": [],
        "annotated_image_path": str(annotated_path),
    }


def test_model_labels_are_normalized_for_detections_and_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = create_valid_image(tmp_path)
    annotated_path = tmp_path / "annotated.jpg"
    model = FakeModel(
        [
            fake_box(0, 0.91, [10.0, 20.0, 110.0, 120.0]),
            fake_box(1, 0.82, [15.0, 25.0, 90.0, 100.0]),
        ],
        names={0: "Disposable plastic container", 1: "Rope & strings"},
    )
    monkeypatch.setattr(yolo_detector, "_load_model", lambda: model)
    monkeypatch.setattr(
        yolo_detector,
        "save_annotated_image",
        lambda _result, _source_path: annotated_path,
    )

    result = yolo_detector.detect_waste(image_path)

    assert result["success"] is True
    assert result["counts"] == {
        "disposable_plastic_container": 1,
        "rope_strings": 1,
    }
    assert result["detections"][0]["class_name"] == "disposable_plastic_container"
    assert result["detections"][1]["class_name"] == "rope_strings"
    assert all(detection["source"] == "yolo" for detection in result["detections"])


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
    monkeypatch.setattr(yolo_detector, "MODEL_PATH", tmp_path / "missing-model.pt")
    monkeypatch.setattr(yolo_detector, "_model", None)

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
    monkeypatch.setattr(
        yolo_detector,
        "save_annotated_image",
        lambda _result, _source_path: tmp_path / "annotated.jpg",
    )

    yolo_detector.detect_waste(image_path)

    assert model.predict_calls[0]["conf"] == 0.35
