"""Audited, serialized transitions for newly assigned collection work."""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.repositories import reports, staff
from app.services.supabase_storage import BUCKET, MEDIA_TYPES, delete_file, put_file


class TaskConflict(RuntimeError):
    pass


class TaskForbidden(PermissionError):
    pass


def _locked_report(db, report_id: str):
    suffix = " FOR UPDATE" if get_settings().persistence_backend == "postgres" else ""
    row = db.execute("SELECT * FROM reports WHERE id = ?" + suffix, (report_id,)).fetchone()
    if row is None:
        raise LookupError("Report not found.")
    return row


def _assignment(db, report_id: str):
    return db.execute("""SELECT * FROM report_assignments WHERE report_id = ?
        AND ended_at IS NULL ORDER BY assigned_at DESC LIMIT 1""", (report_id,)).fetchone()


def _event(db, report_id: str, actor_id: str, previous: str, current: str,
           reason: str | None, *, team: str | None = None, photo: str | None = None) -> str:
    event_id = uuid4().hex
    db.execute("""INSERT INTO report_status_events
        (id, report_id, actor_id, previous_status, new_status, reason, assigned_team, after_photo, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, report_id, actor_id, previous, current, reason, team, photo, reports._utc_now()))
    return event_id


def assign(report_id: str, assignee_id: str, team: str, actor_id: str, reason: str = "") -> dict:
    team = team.strip(); reason = reason.strip()
    if not team or len(team) > 120:
        raise ValueError("Enter a team name (at most 120 characters).")
    db = reports._connect()
    try:
        reports.initialize_database(db); staff.initialize(db)
        db.execute("BEGIN IMMEDIATE")
        row = _locked_report(db, report_id)
        if row["validation_status"] != "valid" or row["status"] not in {"verified", "assigned", "in_progress"}:
            raise TaskConflict("Only a verified or active collection report can be assigned.")
        if row["status"] == "in_progress" and not reason:
            raise ValueError("A reason is required to reassign work in progress or adopt a legacy task.")
        role = db.execute("""SELECT role FROM role_grants WHERE user_id = ? AND revoked_at IS NULL
            AND role IN ('staff','driver') LIMIT 1""", (assignee_id,)).fetchone()
        if role is None:
            raise TaskForbidden("The assignee needs an active staff or driver grant.")
        existing = _assignment(db, report_id)
        if existing and existing["assignee_id"] == assignee_id:
            raise TaskConflict("This task is already assigned to that staff member.")
        if existing and not reason:
            raise ValueError("A reassignment reason is required.")
        now = reports._utc_now()
        if existing:
            db.execute("UPDATE report_assignments SET ended_at = ? WHERE id = ?", (now, existing["id"]))
        assignment_id = str(uuid4())
        db.execute("""INSERT INTO report_assignments(id, report_id, team_name, assignee_id, assigned_by, assigned_at)
            VALUES (?, ?, ?, ?, ?, ?)""", (assignment_id, report_id, team, assignee_id, actor_id, now))
        db.execute("UPDATE reports SET status = 'assigned', assigned_team = ?, updated_at = ? WHERE id = ?",
                   (team, now, report_id))
        event_id = _event(db, report_id, actor_id, row["status"], "assigned", reason or f"Assigned to {team}", team=team)
        if row["notification_email"] and get_settings().notify_citizen_on_assignment:
            reports._queue_email(db, report_id, "assigned", row["notification_email"], now, event_id=event_id)
        db.commit()
        return {"report_id": report_id, "status": "assigned", "assignment_id": assignment_id}
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


def change(report_id: str, action: str, actor_id: str, *, reason: str = "",
           proof_source: Path | None = None, note: str = "") -> dict:
    allowed = {
        "start": ("assigned", "in_progress", "staff"),
        "submit": ("in_progress", "pending_verification", "staff"),
        "verify": ("pending_verification", "resolved", "admin"),
        "rework": ("pending_verification", "in_progress", "admin"),
        "reject": ("pending_verification", "rejected", "admin"),
    }
    if action not in allowed:
        raise ValueError("Unsupported collection action.")
    previous, current, actor_kind = allowed[action]
    reason = reason.strip(); note = note.strip()
    if action in {"rework", "reject"} and not reason:
        raise ValueError("A reason is required for rejection or rework.")
    if action == "submit" and (proof_source is None or not note or len(note) > 2000):
        raise ValueError("A cleanup photo and note are required.")
    db = reports._connect(); local_file: Path | None = None; storage_key: str | None = None
    try:
        reports.initialize_database(db); staff.initialize(db)
        db.execute("BEGIN IMMEDIATE")
        row = _locked_report(db, report_id)
        assignment = _assignment(db, report_id)
        if row["status"] != previous or assignment is None:
            raise TaskConflict(f"Task must be {previous.replace('_', ' ')} before {action}.")
        if action == "verify" and db.execute(
            "SELECT 1 FROM cleanup_proofs WHERE report_id = ? AND assignment_id = ? LIMIT 1",
            (report_id, assignment["id"])).fetchone() is None:
            raise TaskConflict("Cleanup proof is required before verification.")
        if actor_kind == "staff":
            grant = db.execute("""SELECT 1 FROM role_grants WHERE user_id = ?
                AND role IN ('staff','driver') AND revoked_at IS NULL LIMIT 1""", (actor_id,)).fetchone()
            if assignment["assignee_id"] != actor_id or grant is None:
                raise TaskForbidden("Only the assigned staff member may update this task.")
        now = reports._utc_now(); photo_url: str | None = None
        if action == "submit":
            assert proof_source is not None
            if not proof_source.is_file() or proof_source.suffix.lower() not in MEDIA_TYPES:
                raise ValueError("A validated cleanup photo is required.")
            proof_id = uuid4().hex
            name = f"{proof_id}{proof_source.suffix.lower()}"
            storage_key = f"cleanup/{report_id}/{name}"
            if get_settings().persistence_backend == "postgres":
                content_type, digest, size = put_file(storage_key, proof_source)
            else:
                local_file = reports.REPORT_ASSETS_DIR / "cleanup" / report_id / name
                local_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(proof_source, local_file)
                data = proof_source.read_bytes(); digest = hashlib.sha256(data).hexdigest(); size = len(data)
                content_type = MEDIA_TYPES[proof_source.suffix.lower()]
            photo_url = f"/api/collection/tasks/{report_id}/proof/{proof_id}"
            db.execute("""INSERT INTO cleanup_proofs
                (id, report_id, assignee_id, assignment_id, object_key, content_type, sha256, byte_size, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (proof_id, report_id, actor_id, assignment["id"], storage_key,
                 content_type, digest, size, note, now))
        seconds = None
        if action == "verify":
            raw_submitted = row["created_at"]
            submitted = raw_submitted if isinstance(raw_submitted, datetime) else datetime.fromisoformat(raw_submitted.replace("Z", "+00:00"))
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
            seconds = max(0, int((datetime.now(timezone.utc) - submitted).total_seconds()))
        updated = db.execute("""UPDATE reports SET status = ?, updated_at = ?,
            after_photo = COALESCE(?, after_photo), resolution_seconds = COALESCE(?, resolution_seconds),
            resolution_details = COALESCE(?, resolution_details)
            WHERE id = ? AND status = ?""", (current, now, photo_url, seconds,
                                           note if action == "submit" else None, report_id, previous))
        if updated.rowcount != 1:
            raise TaskConflict("Task changed while this action was being saved.")
        event_reason = reason or (note if action == "submit" else
                                  "Collection started" if action == "start" else
                                  "Cleanup proof verified" if action == "verify" else None)
        event_id = _event(db, report_id, actor_id, previous, current, event_reason,
                          team=assignment["team_name"], photo=photo_url)
        if row["notification_email"] and (action == "verify" or
                (action in {"start", "submit"} and get_settings().notify_citizen_on_progress)):
            reports._queue_email(db, report_id, current, row["notification_email"], now, event_id=event_id)
        if action in {"verify", "reject"}:
            db.execute("UPDATE report_assignments SET ended_at = ? WHERE id = ?", (now, assignment["id"]))
        db.commit()
        return {"report_id": report_id, "status": current, "resolution_seconds": seconds, "after_photo": photo_url}
    except Exception:
        db.rollback()
        if local_file: local_file.unlink(missing_ok=True)
        if storage_key and get_settings().persistence_backend == "postgres":
            try: delete_file(storage_key, bucket=BUCKET)
            except Exception: pass
        raise
    finally:
        db.close()


def tasks_for(user_id: str) -> list[dict]:
    with reports._connect() as db:
        staff.initialize(db)
        rows = db.execute("""SELECT r.id, r.reference, r.title, r.location, r.status, r.category,
            r.created_at, a.id AS assignment_id, a.team_name, a.assigned_at
            FROM report_assignments a JOIN reports r ON r.id = a.report_id
            WHERE a.assignee_id = ? AND a.ended_at IS NULL ORDER BY a.assigned_at DESC""", (user_id,)).fetchall()
        return [dict(row) for row in rows]


def task_for(report_id: str, user_id: str, *, admin: bool = False) -> dict:
    with reports._connect() as db:
        staff.initialize(db)
        assignment = _assignment(db, report_id)
        if assignment is None or (not admin and assignment["assignee_id"] != user_id):
            raise LookupError("Task not found.")
    report = reports.get_report(report_id)
    assert report is not None
    if admin:
        return report | {"assignment": dict(assignment)}
    limited = {key: report.get(key) for key in (
        "id", "reference", "title", "summary", "location", "latitude", "longitude",
        "category", "status", "assigned_team", "original_image", "annotated_image",
        "after_photo", "status_events", "created_at", "updated_at")}
    for field in ("original_image", "annotated_image"):
        value = limited[field]
        if value:
            limited[field] = f"/api/collection/tasks/{report_id}/image/{Path(value).name}"
    return limited | {"assignment": dict(assignment)}
