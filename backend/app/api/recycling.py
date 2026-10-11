"""Registered recycling points and administrative management."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.auth import AuthenticatedUser, require_admin_user, require_authenticated_user
from app.core.config import get_settings
from app.repositories import reports
from app.repositories.identities import activity_affiliation
from app.repositories.recycling_actions import (
    ActionConflict, ActionForbidden, ActionNotFound, create_action, get_action,
    list_own_actions, list_pending_actions, review_action,
)
from app.repositories.reports import _connect, initialize_database
from app.api.reports import ConfirmedWasteItem
from app.services.ai.category_mapping import get_category_metadata
from app.services.ai.image_validation import ImageValidationError, validate_image
from app.services.image_uploads import (
    MAX_UPLOAD_SIZE, UploadMetadataError, create_unique_upload_path,
    save_image_upload, upload_size_limit_message, validate_image_upload_metadata,
)

router = APIRouter()
logger = logging.getLogger(__name__)
ACTION_ID = re.compile(r"^[0-9a-f]{32}$")
ACTION_IMAGE = re.compile(r"^(?:original|proof)\.(?:jpg|jpeg|png|webp)$")
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class RecyclingPointInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accepted_materials: list[str] = Field(min_length=1, max_length=30)
    description: str = Field(default="", max_length=2000)
    active: bool = True

    @field_validator("name", "description")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Point name is required.")
        return value

    @field_validator("accepted_materials")
    @classmethod
    def normalize_materials(cls, values: list[str]) -> list[str]:
        materials: list[str] = []
        seen: set[str] = set()
        for value in values:
            material = value.strip()
            if not material or len(material) > 80:
                raise ValueError("Each material must be 1 to 80 characters.")
            if material.casefold() not in seen:
                materials.append(material)
                seen.add(material.casefold())
        return materials


class RecyclingSubmission(BaseModel):
    analysis_id: str = Field(min_length=1, max_length=64)
    recycling_point_id: str = Field(min_length=1, max_length=100)
    confirmed_items: list[ConfirmedWasteItem] = Field(min_length=1, max_length=100)
    proof_location_source: str
    proof_latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    proof_longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    proof_location: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_evidence(self) -> "RecyclingSubmission":
        if self.proof_location_source == "gps":
            if self.proof_latitude is None or self.proof_longitude is None:
                raise ValueError("Capture both GPS coordinates for a GPS proof location.")
        elif self.proof_location_source == "manual":
            if not (self.proof_location or "").strip() or self.proof_latitude is not None or self.proof_longitude is not None:
                raise ValueError("Enter a manual proof location without GPS coordinates.")
        else:
            raise ValueError("Proof location source must be GPS or manual.")
        for item in self.confirmed_items:
            rule = get_category_metadata(item.name)
            if rule["waste_category"] != "Unknown":
                if rule["waste_category"] != "Recyclable Waste" or item.category != "Recyclable Waste":
                    raise ValueError("Only confirmed recyclable waste can create a recycling action.")
                item.material = rule["material"]
            elif item.category != "Recyclable Waste" or not item.material.strip() or item.material.strip().casefold() == "unknown":
                raise ValueError("Confirm the material for every recyclable item.")
        return self


class RecyclingReview(BaseModel):
    decision: str
    rejection_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_decision(self) -> "RecyclingReview":
        if self.decision not in {"verified", "rejected"}:
            raise ValueError("Decision must be verified or rejected.")
        if self.decision == "rejected" and not (self.rejection_reason or "").strip():
            raise ValueError("A rejection reason is required.")
        return self


def _serialize(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"], "name": row["name"],
        "latitude": row["latitude"], "longitude": row["longitude"],
        "accepted_materials": json.loads(row["accepted_materials_json"]),
        "description": row["description"], "active": bool(row["active"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _list_points(*, active_only: bool) -> list[dict[str, object]]:
    with _connect() as database:
        initialize_database(database)
        rows = database.execute(
            """SELECT * FROM recycling_points WHERE data_origin = 'production'
               AND (? = 0 OR active = 1) ORDER BY name COLLATE NOCASE, id""",
            (int(active_only),),
        ).fetchall()
        return [_serialize(row) for row in rows]


def _save_point(point: RecyclingPointInput, point_id: str | None) -> dict[str, object] | None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as database:
        initialize_database(database)
        database.execute("BEGIN IMMEDIATE")
        if point_id is None:
            point_id = str(uuid4())
            database.execute(
                """INSERT INTO recycling_points
                   (id, name, latitude, longitude, accepted_materials_json,
                    description, active, data_origin, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'production', ?, ?)""",
                (point_id, point.name, point.latitude, point.longitude,
                 json.dumps(point.accepted_materials), point.description, int(point.active), now, now),
            )
        else:
            cursor = database.execute(
                """UPDATE recycling_points SET name = ?, latitude = ?, longitude = ?,
                   accepted_materials_json = ?, description = ?, active = ?, updated_at = ?
                   WHERE id = ? AND data_origin = 'production'""",
                (point.name, point.latitude, point.longitude, json.dumps(point.accepted_materials),
                 point.description, int(point.active), now, point_id),
            )
            if cursor.rowcount == 0:
                database.rollback()
                return None
        row = database.execute("SELECT * FROM recycling_points WHERE id = ?", (point_id,)).fetchone()
        database.commit()
        return _serialize(row)


@router.get("/points")
async def read_recycling_points(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> list[dict[str, object]]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Participant access is required.")
    return await run_in_threadpool(_list_points, active_only=True)


@router.get("/admin/points")
async def admin_list_recycling_points(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> list[dict[str, object]]:
    return await run_in_threadpool(_list_points, active_only=False)


@router.post("/admin/points", status_code=201)
async def admin_create_recycling_point(
    point: RecyclingPointInput,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    result = await run_in_threadpool(_save_point, point, None)
    assert result is not None
    return result


@router.put("/admin/points/{point_id}")
async def admin_update_recycling_point(
    point_id: str,
    point: RecyclingPointInput,
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    result = await run_in_threadpool(_save_point, point, point_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Recycling point not found.")
    return result


@router.post("/actions", status_code=201)
async def submit_recycling_action(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    payload: str = Form(...),
    proof: UploadFile = File(...),
) -> dict[str, object]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Participant access is required.")
    try:
        submission = RecyclingSubmission.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_context=False)) from exc
    try:
        extension = validate_image_upload_metadata(proof.filename, proof.content_type)
    except UploadMetadataError as exc:
        await proof.close()
        raise HTTPException(status_code=415, detail="Use one JPG, PNG, or WEBP proof photo with a matching filename and type.") from exc
    try:
        destination = create_unique_upload_path(get_settings().upload_dir, prefix="recycling-proof", extension=extension)
    except (OSError, ValueError) as exc:
        await proof.close()
        raise HTTPException(status_code=500, detail="The proof photo could not be stored.") from exc
    try:
        await save_image_upload(proof, destination)
        await run_in_threadpool(validate_image, destination)
        data = submission.model_dump()
        data["user_id"] = user["id"]
        data["activity_affiliation"] = activity_affiliation(user["id"], user.get("claimed_affiliation"))
        return await run_in_threadpool(create_action, data, destination)
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.public_message) from exc
    except ValueError as exc:
        if str(exc) == "IMAGE_TOO_LARGE":
            raise HTTPException(status_code=413, detail=upload_size_limit_message(MAX_UPLOAD_SIZE)) from exc
        raise HTTPException(status_code=400, detail="The proof photo is empty or invalid.") from exc
    except reports.DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except reports.DraftAssetError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ActionForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ActionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        logger.error("recycling_action_storage_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="The recycling action could not be stored. Please try again.") from exc
    finally:
        destination.unlink(missing_ok=True)


@router.get("/actions/me")
async def read_own_actions(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> list[dict[str, object]]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Participant access is required.")
    return await run_in_threadpool(list_own_actions, user["id"])


@router.get("/actions/me/{action_id}")
async def read_own_action(
    action_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, object]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Participant access is required.")
    try:
        return await run_in_threadpool(get_action, action_id, user["id"])
    except ActionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/admin/actions/pending")
async def read_pending_actions(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> list[dict[str, object]]:
    return await run_in_threadpool(list_pending_actions)


@router.post("/admin/actions/{action_id}/review")
async def admin_review_action(
    action_id: str,
    review: RecyclingReview,
    admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    try:
        return await run_in_threadpool(review_action, action_id, review.decision, admin["id"], review.rejection_reason)
    except ActionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="The review could not be saved.") from exc


@router.get("/files/{action_id}/{filename}", response_class=FileResponse)
async def read_action_photo(
    action_id: str,
    filename: str,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> FileResponse:
    if not ACTION_ID.fullmatch(action_id) or not ACTION_IMAGE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Photo not found.")
    try:
        await run_in_threadpool(get_action, action_id, user["id"], admin=user["role"] == "admin")
    except ActionNotFound as exc:
        raise HTTPException(status_code=404, detail="Photo not found.") from exc
    root = (reports.REPORT_ASSETS_DIR / "recycling").resolve()
    photo_path = (root / action_id / filename).resolve()
    if not photo_path.is_relative_to(root) or not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Photo not found.")
    return FileResponse(photo_path, media_type=MEDIA_TYPES[photo_path.suffix.lower()],
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
