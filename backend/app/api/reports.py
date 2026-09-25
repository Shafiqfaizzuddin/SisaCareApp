"""API boundary for permanent waste report submission."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.api.waste_analysis import UPLOAD_DIR
from app.core.auth import (
    AuthenticatedUser,
    get_optional_authenticated_user,
    require_admin_user,
)
from app.repositories import reports as report_repository
from app.repositories.reports import (
    DraftAccessDeniedError,
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
from app.services.image_uploads import (
    MAX_UPLOAD_SIZE,
    UploadMetadataError,
    create_unique_upload_path,
    save_image_upload,
    upload_size_limit_message,
    validate_image_upload_metadata,
)


router = APIRouter()
REPORT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
REPORT_IMAGE_PATTERN = re.compile(r"^(?:original|annotated)\.(?:jpg|jpeg|png|webp)$")
REPORT_MEDIA_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}
REPORT_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


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
async def submit_report(
    submission: ReportSubmission,
    user: Annotated[
        AuthenticatedUser | None,
        Depends(get_optional_authenticated_user),
    ],
) -> dict[str, str]:
    submission_data = _authorize_submission(submission, user)
    return await _create_report(submission_data)


def _authorize_submission(
    submission: ReportSubmission,
    user: AuthenticatedUser | None,
) -> dict[str, object]:
    if submission.reporter_role == "guest":
        if submission.analysis_id is not None:
            raise HTTPException(
                status_code=403,
                detail="AI analysis drafts require an authenticated member.",
            )
        return submission.model_dump()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication is required for member reports.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    submission_data = submission.model_dump()
    submission_data["user_id"] = user["id"]
    submission_data["guest_name"] = None
    submission_data["guest_email"] = None
    return submission_data


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
    except DraftAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DraftAssetError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(
            status_code=500,
            detail="The report could not be stored. Please try again.",
        ) from exc


@router.post("/with-image", status_code=status.HTTP_201_CREATED)
async def submit_report_with_image(
    user: Annotated[
        AuthenticatedUser | None,
        Depends(get_optional_authenticated_user),
    ],
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

    try:
        extension = validate_image_upload_metadata(image.filename, image.content_type)
    except UploadMetadataError:
        await image.close()
        raise HTTPException(
            status_code=415,
            detail=(
                "The image filename, extension, or MIME type is not supported. "
                "Use a JPG, PNG, or WEBP image."
            ),
        )

    submission_data = _authorize_submission(submission, user)
    try:
        destination = create_unique_upload_path(
            UPLOAD_DIR,
            prefix="report",
            extension=extension,
        )
    except (OSError, ValueError) as exc:
        await image.close()
        raise HTTPException(
            status_code=500,
            detail="The image could not be stored.",
        ) from exc
    try:
        await save_image_upload(image, destination)
        await run_in_threadpool(validate_image, destination)
        submission_data["uploaded_image_path"] = str(destination)
        return await _create_report(submission_data)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.public_message) from exc
    except ValueError as exc:
        if str(exc) == "IMAGE_TOO_LARGE":
            raise HTTPException(
                status_code=413,
                detail=upload_size_limit_message(MAX_UPLOAD_SIZE),
            ) from exc
        raise HTTPException(
            status_code=400,
            detail="The uploaded image is empty or invalid.",
        ) from exc
    finally:
        Path(destination).unlink(missing_ok=True)


@router.get("")
async def read_reports(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> list[dict[str, object]]:
    return await run_in_threadpool(list_reports)


@router.post("/{report_id}/validation")
async def validate_submitted_report(
    report_id: str,
    validation: ReportValidation,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
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


@router.get("/files/{report_id}/{filename}", response_class=FileResponse)
async def read_report_image(
    report_id: str,
    filename: str,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> FileResponse:
    if not REPORT_ID_PATTERN.fullmatch(report_id):
        raise HTTPException(status_code=404, detail="Image not found.")
    if not REPORT_IMAGE_PATTERN.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Image not found.")

    report_root = report_repository.REPORT_ASSETS_DIR.resolve()
    image_path = (report_root / report_id / filename).resolve()
    try:
        image_path.relative_to(report_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image not found.") from exc
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(
        image_path,
        media_type=REPORT_MEDIA_TYPES[image_path.suffix.lower()],
        headers=REPORT_MEDIA_HEADERS,
    )


@router.get("/{report_id}")
async def read_report(
    report_id: str,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    report = await run_in_threadpool(get_report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


__all__ = ["router"]
