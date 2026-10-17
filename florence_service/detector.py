"""Single-loaded Florence-2 <OD> inference and strict result normalization."""

from __future__ import annotations

import logging
import math
from time import perf_counter
from typing import Any

from PIL import Image

from .settings import Settings


log = logging.getLogger(__name__)
TASK = "<OD>"


def normalize_detections(parsed: object, width: int, height: int) -> tuple[list[dict], list[str]]:
    """Return x1,y1,x2,y2 pixel edges in the EXIF-corrected image.

    Edges are floating-point coordinates in [0,width] and [0,height].
    Right and bottom edges are exclusive. Invalid or empty boxes are omitted.
    """
    if not isinstance(parsed, dict) or not isinstance(parsed.get(TASK), dict):
        raise ValueError("Florence processor returned no <OD> result.")
    answer = parsed[TASK]
    boxes, labels = answer.get("bboxes"), answer.get("labels")
    if not isinstance(boxes, list) or not isinstance(labels, list) or len(boxes) != len(labels):
        raise ValueError("Florence processor returned mismatched boxes and labels.")
    detections: list[dict] = []
    warnings: list[str] = []
    for index, (box, label) in enumerate(zip(boxes, labels, strict=True)):
        if (
            not isinstance(label, str)
            or not label.strip()
            or not isinstance(box, (list, tuple))
            or len(box) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box)
        ):
            warnings.append(f"Detection {index} had an invalid label or box and was omitted.")
            continue
        x1, y1, x2, y2 = (float(v) for v in box)
        clipped = (
            max(0.0, min(float(width), x1)),
            max(0.0, min(float(height), y1)),
            max(0.0, min(float(width), x2)),
            max(0.0, min(float(height), y2)),
        )
        if clipped != (x1, y1, x2, y2):
            warnings.append(f"Detection {index} box was clipped to image bounds.")
        if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
            warnings.append(f"Detection {index} had an empty box and was omitted.")
            continue
        detections.append({
            "label": label.strip(),
            "bounding_box": dict(zip(("x1", "y1", "x2", "y2"), clipped, strict=True)),
            "confidence": None,
        })
    if boxes and not detections:
        raise ValueError("All Florence detections had invalid boxes or labels.")
    return detections, warnings


class FlorenceDetector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model: Any | None = None
        self.processor: Any | None = None
        self.torch: Any | None = None
        self.device: str | None = None
        self.dtype_name: str | None = None
        self.load_error: str | None = None

    def load(self) -> None:
        """Load the processor and model once. CPU is the fallback if CUDA is unavailable."""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor

            self.torch = torch
            if self.settings.device_preference == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA was requested but is unavailable.")
            use_cuda = self.settings.device_preference != "cpu" and torch.cuda.is_available()
            device = "cuda:0" if use_cuda else "cpu"
            dtype = torch.float16 if device.startswith("cuda") else torch.float32
            log.info("florence_model_loading model=%s revision=%s device=%s dtype=%s",
                     self.settings.model_id, self.settings.model_revision, device, dtype)
            processor = AutoProcessor.from_pretrained(
                self.settings.model_id,
                revision=self.settings.model_revision,
                trust_remote_code=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                self.settings.model_id,
                revision=self.settings.model_revision,
                trust_remote_code=True,
                use_safetensors=True,
                torch_dtype=dtype,
            ).to(device)
            model.eval()
        except Exception as exc:
            self.load_error = f"{type(exc).__name__}: {exc}"
            log.exception("florence_model_load_failed")
            raise
        self.processor = processor
        self.model = model
        self.device = device
        self.dtype_name = "float16" if device.startswith("cuda") else "float32"
        self.load_error = None
        log.info("florence_model_ready device=%s dtype=%s", self.device, self.dtype_name)

    def detect(self, image: Image.Image) -> tuple[list[dict], list[str], int]:
        if self.model is None or self.processor is None or self.torch is None or self.device is None:
            raise RuntimeError("Florence model is not ready.")
        started = perf_counter()
        inputs = self.processor(text=TASK, images=image, return_tensors="pt")
        inputs = inputs.to(self.device, self.torch.float16 if self.device.startswith("cuda") else self.torch.float32)
        with self.torch.inference_mode():
            generated_ids = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=self.settings.max_new_tokens,
                num_beams=self.settings.num_beams,
                do_sample=False,
            )
        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = self.processor.post_process_generation(
            generated_text, task=TASK, image_size=image.size,
        )
        detections, warnings = normalize_detections(parsed, image.width, image.height)
        return detections, warnings, round((perf_counter() - started) * 1000)
