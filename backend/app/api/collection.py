"""Trusted staff grants and the collection workflow API."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.api.waste_analysis import UPLOAD_DIR
from app.api.reports import REPORT_IMAGE_PATTERN, REPORT_MEDIA_TYPES
from app.core.auth import AuthenticatedUser, require_admin_user, require_authenticated_user, require_staff_user
from app.core.config import get_settings
from app.repositories import reports, staff
from app.services.ai.image_validation import ImageValidationError, validate_image
from app.services.collection_workflow import TaskConflict, TaskForbidden, assign, change, task_for, tasks_for
from app.services.image_uploads import (UploadMetadataError, create_unique_upload_path,
                                        save_image_upload, validate_image_upload_metadata)
from app.services.supabase_storage import MEDIA_TYPES, get_file

router = APIRouter()
PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


class StaffGrant(BaseModel):
    user_id: str
    role: Literal["staff", "driver"]


class Assignment(BaseModel):
    assignee_id: str
    team: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=2000)


class Decision(BaseModel):
    reason: str = Field(default="", max_length=2000)


def _problem(exc: Exception) -> HTTPException:
    if isinstance(exc, TaskForbidden): return HTTPException(403, str(exc))
    if isinstance(exc, LookupError): return HTTPException(404, str(exc))
    if isinstance(exc, TaskConflict): return HTTPException(409, str(exc))
    if isinstance(exc, ValueError): return HTTPException(422, str(exc))
    raise exc


async def _ensure_auth_user(user_id: str) -> None:
    try: UUID(user_id)
    except ValueError as exc: raise HTTPException(422, "A valid Supabase Auth user UUID is required.") from exc
    settings = get_settings()
    key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not key:
        raise HTTPException(503, "Supabase Auth administration is not configured.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
                                        headers={"apikey": key, "Authorization": f"Bearer {key}"})
    except httpx.RequestError as exc:
        raise HTTPException(503, "Supabase Auth is unavailable.") from exc
    if response.status_code == 404: raise HTTPException(404, "Supabase Auth user not found.")
    if response.is_error: raise HTTPException(503, "Supabase Auth user lookup failed.")
    try: identity = response.json()
    except ValueError as exc: raise HTTPException(503, "Supabase Auth returned an invalid user.") from exc
    if not isinstance(identity, dict) or identity.get("id") != user_id:
        raise HTTPException(503, "Supabase Auth returned an invalid user.")


@router.get("/admin/staff")
async def list_staff(admin: Annotated[AuthenticatedUser, Depends(require_admin_user)]) -> list[dict]:
    return await run_in_threadpool(staff.list_staff)


@router.post("/admin/staff/grants")
async def grant_staff(grant: StaffGrant, admin: Annotated[AuthenticatedUser, Depends(require_admin_user)]) -> dict:
    await _ensure_auth_user(grant.user_id)
    try: await run_in_threadpool(staff.set_grant, grant.user_id, grant.role, admin["id"])
    except ValueError as exc: raise _problem(exc) from exc
    return {"user_id": grant.user_id, "role": grant.role, "active": True}


@router.delete("/admin/staff/grants/{user_id}/{role}")
async def revoke_staff(user_id: str, role: Literal["staff", "driver"],
                       admin: Annotated[AuthenticatedUser, Depends(require_admin_user)]) -> dict:
    try: await run_in_threadpool(staff.set_grant, user_id, role, admin["id"], revoke=True)
    except ValueError as exc: raise _problem(exc) from exc
    return {"user_id": user_id, "role": role, "active": False}


@router.post("/admin/tasks/{report_id}/assign")
async def assign_task(report_id: str, request: Assignment,
                      admin: Annotated[AuthenticatedUser, Depends(require_admin_user)]) -> dict:
    try: return await run_in_threadpool(assign, report_id, request.assignee_id, request.team, admin["id"], request.reason)
    except (TaskConflict, TaskForbidden, LookupError, ValueError) as exc: raise _problem(exc) from exc


@router.get("/tasks")
async def my_tasks(user: Annotated[AuthenticatedUser, Depends(require_staff_user)]) -> list[dict]:
    return await run_in_threadpool(tasks_for, user["id"])


@router.get("/tasks/{report_id}")
async def my_task(report_id: str, user: Annotated[AuthenticatedUser, Depends(require_staff_user)]) -> dict:
    try: return await run_in_threadpool(task_for, report_id, user["id"])
    except LookupError as exc: raise _problem(exc) from exc


@router.post("/tasks/{report_id}/start")
async def start_task(report_id: str, user: Annotated[AuthenticatedUser, Depends(require_staff_user)]) -> dict:
    try: return await run_in_threadpool(change, report_id, "start", user["id"])
    except (TaskConflict, TaskForbidden, LookupError, ValueError) as exc: raise _problem(exc) from exc


@router.post("/tasks/{report_id}/submit")
async def submit_task(report_id: str, user: Annotated[AuthenticatedUser, Depends(require_staff_user)],
                      note: str = Form(..., min_length=1, max_length=2000), image: UploadFile = File(...)) -> dict:
    destination: Path | None = None
    try:
        try: extension = validate_image_upload_metadata(image.filename, image.content_type)
        except UploadMetadataError as exc: raise HTTPException(415, "Use a JPG, PNG, or WEBP cleanup photo.") from exc
        destination = create_unique_upload_path(UPLOAD_DIR, prefix="cleanup", extension=extension)
        await save_image_upload(image, destination)
        await run_in_threadpool(validate_image, destination)
        return await run_in_threadpool(change, report_id, "submit", user["id"], proof_source=destination, note=note)
    except ImageValidationError as exc: raise HTTPException(400, exc.public_message) from exc
    except ValueError as exc:
        if str(exc) == "IMAGE_TOO_LARGE": raise HTTPException(413, "Cleanup photo exceeds the upload size limit.") from exc
        raise _problem(exc) from exc
    except (TaskConflict, TaskForbidden, LookupError) as exc: raise _problem(exc) from exc
    finally:
        await image.close()
        if destination: destination.unlink(missing_ok=True)


@router.post("/admin/tasks/{report_id}/{action}")
async def review_task(report_id: str, action: Literal["verify", "rework", "reject"], request: Decision,
                      admin: Annotated[AuthenticatedUser, Depends(require_admin_user)]) -> dict:
    try: return await run_in_threadpool(change, report_id, action, admin["id"], reason=request.reason)
    except (TaskConflict, TaskForbidden, LookupError, ValueError) as exc: raise _problem(exc) from exc


@router.get("/tasks/{report_id}/proof/{proof_id}")
async def read_proof(report_id: str, proof_id: str,
                     user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)]) -> Response:
    try:
        with reports._connect() as db:
            staff.initialize(db)
            proof = db.execute("SELECT * FROM cleanup_proofs WHERE id = ? AND report_id = ?", (proof_id, report_id)).fetchone()
            if proof is None: raise HTTPException(404, "Cleanup proof not found.")
            if user["role"] != "admin":
                active = db.execute("SELECT 1 FROM report_assignments WHERE report_id = ? AND assignee_id = ? AND ended_at IS NULL",
                                    (report_id, user["id"])).fetchone()
                if user["role"] != "staff" or proof["assignee_id"] != user["id"] or active is None:
                    raise HTTPException(404, "Cleanup proof not found.")
            object_key, mime = proof["object_key"], proof["content_type"]
        if get_settings().persistence_backend == "postgres":
            data = await run_in_threadpool(get_file, object_key)
            return Response(data, media_type=mime, headers=PRIVATE_HEADERS)
        path = (reports.REPORT_ASSETS_DIR / object_key).resolve()
        path.relative_to(reports.REPORT_ASSETS_DIR.resolve())
        if not path.is_file(): raise HTTPException(404, "Cleanup proof not found.")
        return FileResponse(path, media_type=mime, headers=PRIVATE_HEADERS)
    except ValueError as exc: raise HTTPException(404, "Cleanup proof not found.") from exc


@router.get("/tasks/{report_id}/image/{filename}")
async def read_task_image(report_id: str, filename: str,
                          user: Annotated[AuthenticatedUser, Depends(require_staff_user)]) -> Response:
    if not REPORT_IMAGE_PATTERN.fullmatch(filename): raise HTTPException(404, "Image not found.")
    try: await run_in_threadpool(task_for, report_id, user["id"])
    except LookupError as exc: raise HTTPException(404, "Image not found.") from exc
    if get_settings().persistence_backend == "postgres":
        with reports._connect() as db:
            image = db.execute("SELECT object_key FROM report_images WHERE report_id = ? AND object_key = ?",
                               (report_id, f"reports/{report_id}/{filename}")).fetchone()
        if image is None: raise HTTPException(404, "Image not found.")
        data = await run_in_threadpool(get_file, image["object_key"])
        return Response(data, media_type=REPORT_MEDIA_TYPES[Path(filename).suffix.lower()], headers=PRIVATE_HEADERS)
    path = (reports.REPORT_ASSETS_DIR / report_id / filename).resolve()
    try: path.relative_to(reports.REPORT_ASSETS_DIR.resolve())
    except ValueError as exc: raise HTTPException(404, "Image not found.") from exc
    if not path.is_file(): raise HTTPException(404, "Image not found.")
    return FileResponse(path, media_type=REPORT_MEDIA_TYPES[path.suffix.lower()], headers=PRIVATE_HEADERS)
