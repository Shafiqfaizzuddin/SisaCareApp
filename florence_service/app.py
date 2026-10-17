"""Loopback-only HTTP boundary for local Florence-2 object detection."""

from __future__ import annotations

import asyncio
import io
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from .detector import FlorenceDetector
from .settings import Settings, load_settings


log = logging.getLogger(__name__)
ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def decode_image(data: bytes, content_type: str | None, settings: Settings) -> Image.Image:
    if content_type not in ALLOWED_FORMATS.values():
        raise ValueError("Only JPG, PNG, and WEBP images are supported.")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ALLOWED_FORMATS or ALLOWED_FORMATS[source.format] != content_type:
                raise ValueError("Image contents do not match the declared MIME type.")
            width, height = source.size
            if width < 1 or height < 1 or width > settings.max_image_side or height > settings.max_image_side or width * height > settings.max_image_pixels:
                raise ValueError("Decoded image dimensions exceed the configured limit.")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            image = oriented.convert("RGB")
            if image.width * image.height > settings.max_image_pixels:
                raise ValueError("Oriented image dimensions exceed the configured limit.")
            return image
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The image could not be decoded safely.") from exc


def create_app(settings: Settings | None = None, detector: FlorenceDetector | None = None) -> FastAPI:
    settings = settings or load_settings()
    detector = detector or FlorenceDetector(settings)
    gate = asyncio.Semaphore(1)
    state = {"loading": False}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state["loading"] = True
        async def load_model() -> None:
            try:
                await run_in_threadpool(detector.load)
            except Exception:
                log.exception("florence_startup_model_unavailable")
            finally:
                state["loading"] = False
        task = asyncio.create_task(load_model())
        yield
        if not task.done():
            task.cancel()

    app = FastAPI(title="SisaCare local Florence-2 detection", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict:
        return {
            "service_available": True,
            "model_ready": detector.model is not None and detector.processor is not None,
            "model_loading": state["loading"],
            "model_id": settings.model_id,
            "model_revision": settings.model_revision,
            "device": detector.device,
            "precision": detector.dtype_name,
            "load_error": detector.load_error,
        }

    @app.post("/detect", response_model=None)
    async def detect(image: UploadFile = File(...)) -> dict | JSONResponse:
        analysis_id = uuid4().hex
        started = perf_counter()

        def failure(code: str, message: str, status: int, width: int | None = None, height: int | None = None) -> JSONResponse:
            return JSONResponse(status_code=status, content={
                "success": False, "analysis_id": analysis_id,
                "image_width": width, "image_height": height,
                "model_id": settings.model_id, "model_revision": settings.model_revision,
                "device": detector.device, "precision": detector.dtype_name,
                "detections": [], "processing_time_ms": round((perf_counter() - started) * 1000),
                "warnings": [], "error": {"code": code, "message": message},
            })

        if image.content_type not in ALLOWED_FORMATS.values():
            await image.close()
            return failure("UNSUPPORTED_IMAGE_TYPE", "Only JPG, PNG, and WEBP images are supported.", 415)
        data = bytearray()
        try:
            while chunk := await image.read(min(1024 * 1024, settings.max_upload_bytes + 1 - len(data))):
                data.extend(chunk)
                if len(data) > settings.max_upload_bytes:
                    return failure("IMAGE_TOO_LARGE", "Image exceeds the upload size limit.", 413)
        finally:
            await image.close()
        if not data:
            return failure("INVALID_IMAGE", "Image is empty.", 400)
        try:
            decoded = await run_in_threadpool(decode_image, bytes(data), image.content_type, settings)
        except ValueError as exc:
            return failure("INVALID_IMAGE", str(exc), 400)

        if detector.model is None or detector.processor is None:
            return failure("MODEL_NOT_READY", "Florence model is not ready.", 503, decoded.width, decoded.height)
        try:
            await asyncio.wait_for(gate.acquire(), timeout=settings.queue_timeout_seconds)
        except TimeoutError:
            return failure("INFERENCE_BUSY", "Florence inference is busy; retry shortly.", 503, decoded.width, decoded.height)
        try:
            detections, warnings, _ = await run_in_threadpool(detector.detect, decoded)
        except Exception as exc:
            log.exception("florence_inference_failed analysis_id=%s", analysis_id)
            return failure("INFERENCE_FAILED", f"Florence inference failed ({type(exc).__name__}).", 500, decoded.width, decoded.height)
        finally:
            gate.release()

        if not detections:
            warnings.append("No objects were detected by the <OD> task; review the image manually.")
        return {
            "success": True, "analysis_id": analysis_id,
            "image_width": decoded.width, "image_height": decoded.height,
            "model_id": settings.model_id, "model_revision": settings.model_revision,
            "device": detector.device, "precision": detector.dtype_name,
            "detections": detections,
            "processing_time_ms": round((perf_counter() - started) * 1000),
            "warnings": warnings, "error": None,
        }

    return app


app = create_app()
