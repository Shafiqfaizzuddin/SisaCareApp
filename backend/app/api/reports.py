"""API boundary for permanent waste report submission."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.api.waste_analysis import UPLOAD_DIR
from app.repositories.reports import (
    DraftAlreadySubmittedError,
    DraftAssetError,
    DraftNotFoundError,
    ReportNotFoundError,
    ValidationAlreadyDecidedError,
    create_report,
    get_report,
    list_reports,
    validate_report,
)
from app.services.ai.image_validation import ImageValidationError, validate_image
from app.services.image_uploads import ALLOWED_IMAGE_TYPES, save_image_upload


router = APIRouter()


class ReportSubmission(BaseModel):
    analysis_id: str | None = Field(default=None, min_length=1, max_length=64)
    reporter_role: Literal["guest", "user"]
    user_id: str | None = Field(default=None, max_length=100)
    guest_name: str | None = Field(default=None, max_length=120)
    guest_email: str | None = Field(default=None, max_length=254)
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=4000)
    waste_identified: str = Field(default="", max_length=2000)
    recommended_action: str = Field(default="", max_length=2000)
    environmental_concern: str = Field(default="", max_length=2000)
    category: Literal["household", "recyclable", "construction_debris", "other"]
    location: str = Field(min_length=1, max_length=500)
    site_notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_reporter(self) -> "ReportSubmission":
        if self.reporter_role == "user" and not (self.user_id or "").strip():
            raise ValueError("A user ID is required for member reports.")
        if self.reporter_role == "guest":
            if not (self.guest_name or "").strip():
                raise ValueError("A name is required for guest reports.")
            email = (self.guest_email or "").strip()
            if "@" not in email or email.startswith("@") or email.endswith("@"):
                raise ValueError("A valid email is required for guest reports.")
        return self


class ReportValidation(BaseModel):
    validation_status: Literal["valid", "invalid"]


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_report(submission: ReportSubmission) -> dict[str, str]:
    return await _create_report(submission.model_dump())


async def _create_report(submission: dict[str, object]) -> dict[str, str]:
    try:
        return await run_in_threadpool(
            create_report,
            submission,
        )
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftAlreadySubmittedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DraftAssetError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(
            status_code=500,
            detail="The report could not be stored. Please try again.",
        ) from exc


@router.post("/with-image", status_code=status.HTTP_201_CREATED)
async def submit_report_with_image(
    payload: str = Form(...),
    image: UploadFile = File(...),
) -> dict[str, str]:
    try:
        submission = ReportSubmission.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_context=False),
        ) from exc
    if submission.analysis_id is not None:
        raise HTTPException(
            status_code=400,
            detail="An analyzed report must use its existing analysis draft.",
        )

    extension = ALLOWED_IMAGE_TYPES.get(image.content_type or "")
    if extension is None:
        await image.close()
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Use JPEG, PNG, or WEBP.",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"report-{uuid4().hex}{extension}"
    try:
        await save_image_upload(image, destination)
        await run_in_threadpool(validate_image, destination)
        submission_data = submission.model_dump()
        submission_data["uploaded_image_path"] = str(destination)
        return await _create_report(submission_data)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.public_message) from exc
    except ValueError as exc:
        if str(exc) == "IMAGE_TOO_LARGE":
            raise HTTPException(
                status_code=413,
                detail="The image must be 10 MB or smaller.",
            ) from exc
        raise HTTPException(
            status_code=400,
            detail="The uploaded image is empty or invalid.",
        ) from exc
    finally:
        Path(destination).unlink(missing_ok=True)


@router.get("")
async def read_reports() -> list[dict[str, object]]:
    return await run_in_threadpool(list_reports)


@router.post("/{report_id}/validation")
async def validate_submitted_report(
    report_id: str,
    validation: ReportValidation,
) -> dict[str, object]:
    try:
        return await run_in_threadpool(
            validate_report,
            report_id,
            validation.validation_status,
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="The validation decision could not be stored. Please try again.",
        ) from exc


@router.get("/{report_id}")
async def read_report(report_id: str) -> dict[str, object]:
    report = await run_in_threadpool(get_report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


__all__ = ["router"]
