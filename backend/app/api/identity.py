"""Google sign-in verification and participant affiliation API."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.auth import AuthenticatedUser, get_optional_authenticated_user, require_admin_user, require_authenticated_user
from app.core.config import Settings, get_settings
from app.core.google_identity import ensure_no_automatic_link, verify_google_token
from app.repositories.identities import (
    consume_google_check, create_e_merit_eligibility, pending_matric_reviews,
    read_identity, record_google_check, review_matric, save_google_sub, submit_matric, update_identity,
)


router = APIRouter()


class GoogleToken(BaseModel):
    id_token: str = Field(min_length=100, max_length=10000)


class AffiliationUpdate(BaseModel):
    claimed_affiliation: Literal["student", "staff"]
    matric_number: str | None = None


class MatricSubmission(BaseModel):
    matric_number: str = Field(min_length=1)


class MatricReview(BaseModel):
    decision: Literal["verified", "rejected"]
    verification_method: Literal["authorized_student_record", "prototype_manual"]
    review_reference: str = Field(min_length=1, max_length=500)
    rejection_reason: str | None = Field(default=None, max_length=500)
    procedure_confirmed: bool


@router.post("/google/preflight")
async def google_preflight(body: GoogleToken, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    identity = await run_in_threadpool(verify_google_token, body.id_token, settings)
    existing_user_id = await ensure_no_automatic_link(identity["email"], identity["sub"], settings)
    await run_in_threadpool(
        record_google_check, body.id_token,
        "existing" if existing_user_id else "new", existing_user_id,
    )
    return {"status": "approved"}


@router.post("/google/verify")
async def google_verify_for_link(
    body: GoogleToken,
    _user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    await run_in_threadpool(verify_google_token, body.id_token, settings)
    await run_in_threadpool(record_google_check, body.id_token, "link", _user["id"])
    return {"status": "approved"}


@router.post("/google/complete")
async def google_complete(
    body: GoogleToken,
    user: Annotated[AuthenticatedUser | None, Depends(get_optional_authenticated_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in before completing Google verification.")
    identity = await run_in_threadpool(verify_google_token, body.id_token, settings)
    if user["role"] == "admin":
        raise HTTPException(status_code=403, detail="Google sign-in cannot grant administrator access.")
    if user["google_sub"] != identity["sub"]:
        raise HTTPException(status_code=403, detail="The Google account is not linked to this session.")
    if not user["has_email_identity"] and user["email"].strip().casefold() != identity["email"]:
        raise HTTPException(status_code=403, detail="The Google email does not match this session.")
    checked = await run_in_threadpool(
        consume_google_check, body.id_token, user["id"], has_email_identity=user["has_email_identity"]
    )
    if not checked:
        raise HTTPException(status_code=403, detail="Start Google sign-in or linking from this app.")
    try:
        return await run_in_threadpool(save_google_sub, user["id"], identity["email"], identity["sub"])
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=409, detail="This Google identity is already connected.") from exc


@router.get("/me")
async def get_my_identity(user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)], response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    return await run_in_threadpool(read_identity, user["id"], user["email"], email_verified=user["email_verified"])


@router.put("/me")
async def put_my_identity(
    body: AffiliationUpdate,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, object]:
    matric = body.matric_number.strip() if body.matric_number else None
    if body.claimed_affiliation == "student" and not matric:
        raise HTTPException(status_code=422, detail="Enter a matric number.")
    try:
        return await run_in_threadpool(update_identity, user["id"], user["email"], body.claimed_affiliation, matric)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/me/matric")
async def post_my_matric(
    body: MatricSubmission,
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
    response: Response,
) -> dict[str, object]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Participant access is required.")
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await run_in_threadpool(submit_matric, user["id"], user["email"], body.matric_number)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/admin/matric/pending")
async def get_pending_matric(
    _admin: Annotated[AuthenticatedUser, Depends(require_admin_user)], response: Response,
) -> list[dict[str, object]]:
    response.headers["Cache-Control"] = "private, no-store"
    return await run_in_threadpool(pending_matric_reviews)


@router.post("/admin/matric/{user_id}/review")
async def post_matric_review(
    user_id: str, body: MatricReview,
    admin: Annotated[AuthenticatedUser, Depends(require_admin_user)],
) -> dict[str, object]:
    if not body.procedure_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that you checked an authorized record or agreed manual procedure.")
    try:
        return await run_in_threadpool(
            review_matric, user_id, admin["id"], body.decision,
            body.verification_method, body.review_reference, body.rejection_reason,
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/me/e-merit/eligibility", status_code=201)
async def post_e_merit_eligibility(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> dict[str, object]:
    if user["role"] != "user":
        raise HTTPException(status_code=403, detail="Participant access is required.")
    try:
        return await run_in_threadpool(create_e_merit_eligibility, user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
