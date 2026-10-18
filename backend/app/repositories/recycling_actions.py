"""Persist participant recycling evidence and final administrative decisions."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from app.repositories import reports
from app.core.reward_policy import RECYCLING_POINTS, SPLIT_INCIDENT_CAP, SPLIT_OFFSET_REASON
from app.services.ai.waste_rules import classify_item


class ActionNotFound(LookupError):
    pass


class ActionConflict(RuntimeError):
    pass


class ActionForbidden(PermissionError):
    pass


def _action(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "analysis_id": row["analysis_id"],
        "original_photo": row["original_photo"], "proof_photo": row["proof_photo"],
        "confirmed_waste": json.loads(row["confirmed_waste_json"]),
        "recycling_point_id": row["recycling_point_id"],
        "recycling_point_name": row["recycling_point_name"],
        "proof_latitude": row["proof_latitude"], "proof_longitude": row["proof_longitude"],
        "proof_location": row["proof_location"], "proof_location_source": row["proof_location_source"],
        "verification_status": row["verification_status"],
        "reviewer_id": row["reviewer_id"], "reviewed_at": row["reviewed_at"],
        "rejection_reason": row["rejection_reason"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def _select_action(database: sqlite3.Connection, action_id: str) -> sqlite3.Row | None:
    return database.execute(
        """SELECT a.*, p.name AS recycling_point_name FROM recycling_actions a
           JOIN recycling_points p ON p.id = a.recycling_point_id WHERE a.id = ?""",
        (action_id,),
    ).fetchone()


def create_action(submission: Mapping[str, Any], proof_source: Path) -> dict[str, Any]:
    action_id = uuid4().hex
    now = reports._utc_now()
    directory: Path | None = None
    draft_paths: tuple[Path, Path] | None = None
    database = reports._connect()
    try:
        reports.initialize_database(database)
        database.execute("BEGIN IMMEDIATE")
        draft = database.execute("SELECT * FROM analysis_drafts WHERE id = ?", (submission["analysis_id"],)).fetchone()
        if draft is None:
            raise reports.DraftNotFoundError("The analysis draft does not exist.")
        if draft["user_id"] != submission["user_id"]:
            raise ActionForbidden("This analysis draft does not belong to your account.")
        if database.execute("SELECT 1 FROM recycling_actions WHERE analysis_id = ?", (draft["id"],)).fetchone():
            raise ActionConflict("A recycling action already uses this analysis.")
        split_ids = json.loads(draft["split_recycling_ids_json"]) if draft["split_recycling_ids_json"] else []
        if draft["consumed_at"] is not None:
            submitted_ids = [item.get("review_id") for item in submission["confirmed_items"]]
            if not split_ids or len(submitted_ids) != len(set(submitted_ids)) or set(submitted_ids) != set(split_ids):
                raise ActionConflict("Only the items reserved for recycling in the linked report can use this analysis.")
            linked_report = database.execute("SELECT user_id, confirmed_ai_result_json FROM reports WHERE analysis_id = ?", (draft["id"],)).fetchone()
            if linked_report is None or linked_report["user_id"] != submission["user_id"]:
                raise ActionConflict("The linked report is unavailable.")
            try:
                confirmation = json.loads(linked_report["confirmed_ai_result_json"])
                reviewed = {item["review_id"]: item for item in confirmation["user_corrections"]
                            if item.get("disposition") == "waste"}
            except (TypeError, KeyError, json.JSONDecodeError):
                raise ActionConflict("The linked item confirmation is unavailable.") from None
            for item in submission["confirmed_items"]:
                source = reviewed.get(item["review_id"])
                if (source is None or item["name"].strip() != source["corrected_label"].strip()
                        or item["category"] != source["category"]
                        or item.get("material") != source.get("material")
                        or item.get("quantity") != source.get("quantity")
                        or (item.get("condition_answers") or {}) != (source.get("condition_answers") or {})):
                    raise ActionConflict("Recycling item details differ from the linked confirmation.")
        point = database.execute(
            "SELECT * FROM recycling_points WHERE id = ? AND active = 1 AND data_origin = 'production'",
            (submission["recycling_point_id"],),
        ).fetchone()
        if point is None:
            raise ActionNotFound("The selected recycling point is unavailable.")
        accepted = {material.strip().casefold() for material in json.loads(point["accepted_materials_json"])}
        try:
            draft_payload = json.loads(draft["detection_json"])
        except (TypeError, json.JSONDecodeError):
            draft_payload = {}
        if isinstance(draft_payload, dict) and draft_payload.get("provider") == "florence2":
            for item in submission["confirmed_items"]:
                verdict = classify_item(
                    item["name"], confirmed_material=item.get("material"),
                    answers=item.get("condition_answers") or {},
                    station_accepted_materials=accepted,
                )
                if verdict["category"] != "Recyclable Waste" or verdict["needs_confirmation"]:
                    raise ActionConflict(
                        f"{item['name']} needs confirmed condition and station acceptance before recycling."
                    )
                if verdict["station_material_key"] is None or verdict["station_material_key"].strip().casefold() not in accepted:
                    raise ActionConflict("The selected point does not accept every confirmed material.")
        elif any(item["material"].strip().casefold() not in accepted for item in submission["confirmed_items"]):
            raise ActionConflict("The selected point does not accept every confirmed material.")
        original_source = Path(draft["original_image_path"])
        annotated_source = Path(draft["annotated_image_path"])
        draft_paths = (original_source, annotated_source)
        if not original_source.is_file() or not annotated_source.is_file():
            raise reports.DraftAssetError("The original analysis photo is no longer available. Analyze it again.")
        directory = reports.REPORT_ASSETS_DIR / "recycling" / action_id
        directory.mkdir(parents=True, exist_ok=False)
        original_name = f"original{reports._asset_suffix(original_source)}"
        proof_name = f"proof{reports._asset_suffix(proof_source)}"
        shutil.copy2(original_source, directory / original_name)
        shutil.copy2(proof_source, directory / proof_name)
        activity_key = "sha256:" + hashlib.sha256(original_source.read_bytes()).hexdigest()
        if split_ids:
            activity_key += ":recycling"
        base = f"/api/recycling/files/{action_id}"
        database.execute(
            """INSERT INTO recycling_actions
               (id, user_id, analysis_id, original_photo, confirmed_waste_json,
                recycling_point_id, proof_photo, proof_latitude, proof_longitude,
                proof_location, proof_location_source, activity_key, activity_affiliation,
                verification_status, data_origin, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'production', ?, ?)""",
            (action_id, submission["user_id"], submission["analysis_id"],
             f"{base}/{original_name}", json.dumps({"category": "Recyclable Waste", "items": submission["confirmed_items"]}),
             point["id"], f"{base}/{proof_name}", submission.get("proof_latitude"),
             submission.get("proof_longitude"), submission.get("proof_location"),
             submission["proof_location_source"], activity_key,
             submission["activity_affiliation"], now, now),
        )
        database.execute("UPDATE analysis_drafts SET consumed_at = ? WHERE id = ?", (now, draft["id"]))
        result = _action(_select_action(database, action_id))
        database.commit()
    except Exception:
        database.rollback()
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        database.close()
    if draft_paths is not None:
        for path in draft_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # Permanent evidence is committed; temporary cleanup is best effort.
    return result


def list_own_actions(user_id: str) -> list[dict[str, Any]]:
    with reports._connect() as database:
        reports.initialize_database(database)
        rows = database.execute(
            """SELECT a.*, p.name AS recycling_point_name FROM recycling_actions a
               JOIN recycling_points p ON p.id = a.recycling_point_id
               WHERE a.user_id = ? AND a.data_origin = 'production'
               ORDER BY a.created_at DESC""", (user_id,),
        ).fetchall()
        return [_action(row) for row in rows]


def get_action(action_id: str, user_id: str, *, admin: bool = False) -> dict[str, Any]:
    with reports._connect() as database:
        reports.initialize_database(database)
        row = _select_action(database, action_id)
        if row is None or row["data_origin"] != "production":
            raise ActionNotFound("Recycling action not found.")
        if not admin and row["user_id"] != user_id:
            raise ActionNotFound("Recycling action not found.")
        return _action(row)


def list_pending_actions() -> list[dict[str, Any]]:
    with reports._connect() as database:
        reports.initialize_database(database)
        rows = database.execute(
            """SELECT a.*, p.name AS recycling_point_name FROM recycling_actions a
               JOIN recycling_points p ON p.id = a.recycling_point_id
               WHERE a.verification_status = 'pending' AND a.data_origin = 'production'
               ORDER BY a.created_at"""
        ).fetchall()
        return [_action(row) | {"user_id": row["user_id"]} for row in rows]


def review_action(action_id: str, decision: str, reviewer_id: str, reason: str | None) -> dict[str, Any]:
    now = reports._utc_now()
    database = reports._connect()
    try:
        reports.initialize_database(database)
        database.execute("BEGIN IMMEDIATE")
        row = _select_action(database, action_id)
        if row is None or row["data_origin"] != "production":
            raise ActionNotFound("Recycling action not found.")
        if row["verification_status"] != "pending":
            raise ActionConflict("This recycling action has already been reviewed.")
        if decision == "verified" and reports.other_incident_has_award(database, row["activity_key"], row["analysis_id"]):
            raise ActionConflict("Another incident using this photo has already earned points.")
        if decision == "verified" and database.execute(
            "SELECT 1 FROM reward_events WHERE activity_key = ? AND transaction_type IN ('report_award', 'recycling_award')",
            (row["activity_key"],),
        ).fetchone():
            raise ActionConflict("This underlying activity has already earned points. Reject the duplicate submission.")
        database.execute(
            """UPDATE recycling_actions SET verification_status = ?, reviewer_id = ?,
               reviewed_at = ?, rejection_reason = ?, updated_at = ? WHERE id = ?""",
            (decision, reviewer_id, now, reason if decision == "rejected" else None, now, action_id),
        )
        result = _action(_select_action(database, action_id)) | {"reward_points": 0}
        database.commit()
        return result
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()
