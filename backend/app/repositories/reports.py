"""SQLite persistence for analysis drafts and submitted waste reports."""

from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from app.core.config import get_settings
from app.core.reward_policy import REPORT_POINTS, SPLIT_OFFSET_REASON
from app.services.ai.waste_rules import classify_item
from app.services.ai.grouping_service import group_report_observations


_settings = get_settings()
DATABASE_PATH = _settings.database_path
REPORT_ASSETS_DIR = _settings.report_assets_dir
REPORT_ASSET_URL_PREFIX = "/api/reports/files"
REPORT_VALIDATION_REWARD_POINTS = REPORT_POINTS


class DraftNotFoundError(LookupError):
    """Raised when a submitted analysis draft does not exist."""


class DraftAlreadySubmittedError(RuntimeError):
    """Raised when an analysis draft has already created a report."""


class DraftAssetError(RuntimeError):
    """Raised when a draft image is no longer available."""


class DraftAccessDeniedError(PermissionError):
    """Raised when a user attempts to consume another user's AI draft."""


class ReviewValidationError(ValueError):
    """Raised when submitted confirmation does not match the saved detections."""


class ReportNotFoundError(LookupError):
    """Raised when an administrative report action targets a missing report."""


class ValidationAlreadyDecidedError(RuntimeError):
    """Raised when an administrator tries to reverse a validation decision."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection | None = None) -> None:
    """Create the local report tables when they do not exist."""
    owns_connection = connection is None
    database = connection or _connect()
    try:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS analysis_drafts (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                original_image_path TEXT NOT NULL,
                annotated_image_path TEXT NOT NULL,
                detection_json TEXT NOT NULL,
                ai_report_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                consumed_at TEXT
                ,split_recycling_ids_json TEXT
            );

            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                reference TEXT NOT NULL UNIQUE,
                analysis_id TEXT UNIQUE,
                reporter_role TEXT NOT NULL,
                user_id TEXT,
                guest_name TEXT,
                guest_email TEXT,
                original_image TEXT,
                annotated_image TEXT,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                waste_identified TEXT NOT NULL DEFAULT '',
                recommended_action TEXT NOT NULL DEFAULT '',
                environmental_concern TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                final_categories_json TEXT NOT NULL DEFAULT '[]',
                ai_analysis_json TEXT,
                location TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                location_address TEXT,
                location_address_source TEXT,
                location_street TEXT,
                location_city TEXT,
                location_state TEXT,
                location_postcode TEXT,
                location_country TEXT,
                location_source TEXT,
                site_notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                validation_status TEXT NOT NULL DEFAULT 'pending',
                validated_at TEXT,
                reviewer_id TEXT,
                reviewed_at TEXT,
                rejection_reason TEXT,
                confirmed_ai_result_json TEXT,
                activity_key TEXT,
                data_origin TEXT NOT NULL DEFAULT 'legacy_unknown'
                    CHECK (data_origin IN ('production', 'demo', 'legacy_unknown')),
                activity_affiliation TEXT NOT NULL DEFAULT 'unknown',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (analysis_id) REFERENCES analysis_drafts(id)
            );

            CREATE TABLE IF NOT EXISTS waste_detections (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                class_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                waste_category TEXT NOT NULL,
                material TEXT NOT NULL,
                confidence REAL,
                x1 REAL,
                y1 REAL,
                x2 REAL,
                y2 REAL,
                source TEXT NOT NULL DEFAULT 'yolo',
                created_at TEXT NOT NULL,
                FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_waste_detections_report_id
                ON waste_detections(report_id);

            CREATE TABLE IF NOT EXISTS report_status_events (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE RESTRICT,
                actor_id TEXT NOT NULL,
                previous_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                reason TEXT,
                assigned_team TEXT,
                resolution_details TEXT,
                after_photo TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_report_status_events_report
                ON report_status_events(report_id, created_at);

            CREATE TABLE IF NOT EXISTS recycling_points (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
                longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
                accepted_materials_json TEXT NOT NULL
                    CHECK (json_valid(accepted_materials_json) AND json_type(accepted_materials_json) = 'array'),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                description TEXT NOT NULL DEFAULT '',
                address TEXT,
                address_source TEXT,
                access_notes TEXT NOT NULL DEFAULT '',
                opening_hours TEXT NOT NULL DEFAULT '',
                data_origin TEXT NOT NULL DEFAULT 'production'
                    CHECK (data_origin IN ('production', 'demo')),
                public_verified INTEGER NOT NULL DEFAULT 0 CHECK (public_verified IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recycling_actions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                analysis_id TEXT UNIQUE REFERENCES analysis_drafts(id),
                original_photo TEXT,
                confirmed_waste_json TEXT NOT NULL CHECK (json_valid(confirmed_waste_json)),
                recycling_point_id TEXT NOT NULL REFERENCES recycling_points(id),
                proof_photo TEXT NOT NULL CHECK (length(trim(proof_photo)) > 0),
                proof_latitude REAL CHECK (proof_latitude BETWEEN -90 AND 90),
                proof_longitude REAL CHECK (proof_longitude BETWEEN -180 AND 180),
                proof_location TEXT,
                proof_location_source TEXT CHECK (proof_location_source IN ('gps', 'manual')),
                activity_key TEXT NOT NULL,
                activity_affiliation TEXT NOT NULL DEFAULT 'unknown'
                    CHECK (activity_affiliation IN ('student', 'staff', 'unknown')),
                verification_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (verification_status IN ('pending', 'verified', 'rejected')),
                reviewer_id TEXT,
                reviewed_at TEXT,
                rejection_reason TEXT,
                data_origin TEXT NOT NULL DEFAULT 'production'
                    CHECK (data_origin IN ('production', 'demo')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (original_photo IS NOT NULL OR analysis_id IS NOT NULL),
                CHECK ((proof_latitude IS NULL) = (proof_longitude IS NULL)),
                CHECK (proof_latitude IS NOT NULL OR length(trim(COALESCE(proof_location, ''))) > 0),
                CHECK (verification_status = 'pending' OR (reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)),
                CHECK (verification_status != 'rejected' OR rejection_reason IS NOT NULL)
            );

            CREATE INDEX IF NOT EXISTS idx_recycling_points_active
                ON recycling_points(active, data_origin);
            CREATE INDEX IF NOT EXISTS idx_recycling_actions_participant
                ON recycling_actions(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_recycling_actions_review
                ON recycling_actions(verification_status, created_at);

            CREATE TABLE IF NOT EXISTS reward_events (
                id TEXT PRIMARY KEY,
                report_id TEXT UNIQUE REFERENCES reports(id) ON DELETE RESTRICT,
                recycling_action_id TEXT UNIQUE REFERENCES recycling_actions(id) ON DELETE RESTRICT,
                user_id TEXT NOT NULL,
                signed_amount INTEGER NOT NULL CHECK (signed_amount != 0),
                points INTEGER NOT NULL CHECK (points = signed_amount),
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('report_award', 'recycling_award', 'adjustment')),
                source_activity_type TEXT NOT NULL CHECK (source_activity_type IN ('report', 'recycling_action', 'manual')),
                source_activity_id TEXT NOT NULL,
                activity_key TEXT,
                reason TEXT NOT NULL,
                activity_affiliation TEXT NOT NULL DEFAULT 'unknown'
                    CHECK (activity_affiliation IN ('student', 'staff', 'unknown')),
                e_merit_classification TEXT NOT NULL DEFAULT 'ineligible_unknown'
                    CHECK (e_merit_classification IN ('eligible_student', 'ineligible_staff', 'ineligible_unknown', 'legacy_unclassified')),
                audit_reference TEXT NOT NULL,
                reviewer_id TEXT,
                data_origin TEXT NOT NULL DEFAULT 'production'
                    CHECK (data_origin IN ('production', 'demo', 'legacy_unknown')),
                created_at TEXT NOT NULL,
                CHECK (
                    (transaction_type = 'report_award' AND report_id IS NOT NULL
                     AND recycling_action_id IS NULL AND signed_amount > 0
                     AND source_activity_type = 'report' AND source_activity_id = report_id)
                    OR (transaction_type = 'recycling_award' AND recycling_action_id IS NOT NULL
                     AND report_id IS NULL AND signed_amount > 0
                     AND source_activity_type = 'recycling_action' AND source_activity_id = recycling_action_id)
                    OR (transaction_type = 'adjustment' AND report_id IS NULL
                     AND recycling_action_id IS NULL)
                ),
                CHECK (transaction_type = 'adjustment' OR activity_key IS NOT NULL),
                CHECK (e_merit_classification != 'eligible_student' OR
                       (transaction_type != 'adjustment' AND activity_affiliation = 'student'
                        AND data_origin = 'production')),
                CHECK (transaction_type != 'report_award' OR signed_amount = 2),
                CHECK (transaction_type != 'recycling_award' OR signed_amount = 5)
            );

            CREATE INDEX IF NOT EXISTS idx_reward_events_user_id
                ON reward_events(user_id);

            CREATE TABLE IF NOT EXISTS public_participants (
                user_id TEXT PRIMARY KEY,
                public_name TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
                visible INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0, 1)),
                disabled INTEGER NOT NULL DEFAULT 0 CHECK (disabled IN (0, 1)),
                deleted INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1)),
                data_origin TEXT NOT NULL DEFAULT 'production'
                    CHECK (data_origin IN ('production', 'demo'))
            );
            """
        )
        _ensure_analysis_draft_owner_column(database)
        if "split_recycling_ids_json" not in {row["name"] for row in database.execute("PRAGMA table_info(analysis_drafts)")}:
            database.execute("ALTER TABLE analysis_drafts ADD COLUMN split_recycling_ids_json TEXT")
        _ensure_report_validation_columns(database)
        _ensure_report_location_columns(database)
        _ensure_community_report_columns(database)
        _ensure_report_ai_columns(database)
        _ensure_campus_columns(database)
        _ensure_recycling_action_columns(database)
        _ensure_waste_detection_storage(database)
        _migrate_legacy_report_detections(database)
        database.commit()
    finally:
        if owns_connection:
            database.close()


def _ensure_report_validation_columns(database: sqlite3.Connection) -> None:
    """Add validation fields to databases created before rewards were persisted."""
    columns = {
        row["name"] for row in database.execute("PRAGMA table_info(reports)")
    }
    if "validation_status" not in columns:
        database.execute(
            "ALTER TABLE reports ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'pending'"
        )
    if "validated_at" not in columns:
        database.execute("ALTER TABLE reports ADD COLUMN validated_at TEXT")


def _ensure_analysis_draft_owner_column(database: sqlite3.Connection) -> None:
    """Add draft ownership to databases created before authenticated analysis."""

    columns = {
        row["name"] for row in database.execute("PRAGMA table_info(analysis_drafts)")
    }
    if "user_id" not in columns:
        database.execute("ALTER TABLE analysis_drafts ADD COLUMN user_id TEXT")


def _ensure_recycling_action_columns(database: sqlite3.Connection) -> None:
    columns = {row["name"] for row in database.execute("PRAGMA table_info(recycling_actions)")}
    if "proof_location_source" not in columns:
        database.execute("ALTER TABLE recycling_actions ADD COLUMN proof_location_source TEXT")


def _ensure_report_location_columns(database: sqlite3.Connection) -> None:
    """Add structured location fields without invalidating historical reports."""

    columns = {
        row["name"] for row in database.execute("PRAGMA table_info(reports)")
    }
    definitions = {
        "latitude": "REAL",
        "longitude": "REAL",
        "location_address": "TEXT",
        "location_address_source": "TEXT",
        "location_street": "TEXT",
        "location_city": "TEXT",
        "location_state": "TEXT",
        "location_postcode": "TEXT",
        "location_country": "TEXT",
        "location_source": "TEXT",
    }
    for name, data_type in definitions.items():
        if name not in columns:
            database.execute(f"ALTER TABLE reports ADD COLUMN {name} {data_type}")


def _ensure_community_report_columns(database: sqlite3.Connection) -> None:
    columns = {row["name"] for row in database.execute("PRAGMA table_info(reports)")}
    for name in ("assigned_team", "resolution_details", "after_photo"):
        if name not in columns:
            database.execute(f"ALTER TABLE reports ADD COLUMN {name} TEXT")


def _ensure_report_ai_columns(database: sqlite3.Connection) -> None:
    """Add immutable server-owned AI facts to previously created databases."""

    columns = {
        row["name"] for row in database.execute("PRAGMA table_info(reports)")
    }
    if "final_categories_json" not in columns:
        database.execute(
            "ALTER TABLE reports ADD COLUMN final_categories_json "
            "TEXT NOT NULL DEFAULT '[]'"
        )
    if "ai_analysis_json" not in columns:
        database.execute("ALTER TABLE reports ADD COLUMN ai_analysis_json TEXT")


def _ensure_campus_columns(database: sqlite3.Connection) -> None:
    """Extend existing rows conservatively; historical points stay unclassified."""
    report_columns = {row["name"] for row in database.execute("PRAGMA table_info(reports)")}
    report_additions = {
        "activity_affiliation": "TEXT NOT NULL DEFAULT 'unknown'",
        "reviewer_id": "TEXT",
        "reviewed_at": "TEXT",
        "rejection_reason": "TEXT",
        "confirmed_ai_result_json": "TEXT",
        "activity_key": "TEXT",
        "data_origin": "TEXT NOT NULL DEFAULT 'legacy_unknown'",
    }
    for name, definition in report_additions.items():
        if name not in report_columns:
            database.execute(f"ALTER TABLE reports ADD COLUMN {name} {definition}")
    point_columns = {row["name"] for row in database.execute("PRAGMA table_info(recycling_points)")}
    for name, definition in {
        "address": "TEXT", "address_source": "TEXT",
        "access_notes": "TEXT NOT NULL DEFAULT ''", "opening_hours": "TEXT NOT NULL DEFAULT ''",
        "public_verified": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if name not in point_columns:
            database.execute(f"ALTER TABLE recycling_points ADD COLUMN {name} {definition}")
    if "user_id" in report_columns:
        database.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_participant ON reports(user_id, created_at)"
        )
    if "created_at" in report_columns:
        database.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_review ON reports(validation_status, created_at)"
        )
    reward_columns = {row["name"] for row in database.execute("PRAGMA table_info(reward_events)")}
    reward_additions = {
        "activity_affiliation": "TEXT NOT NULL DEFAULT 'unknown'",
        "recycling_action_id": "TEXT REFERENCES recycling_actions(id)",
        "signed_amount": "INTEGER",
        "transaction_type": "TEXT NOT NULL DEFAULT 'report_award'",
        "source_activity_type": "TEXT NOT NULL DEFAULT 'report'",
        "source_activity_id": "TEXT",
        "activity_key": "TEXT",
        "e_merit_classification": "TEXT NOT NULL DEFAULT 'legacy_unclassified'",
        "audit_reference": "TEXT",
        "reviewer_id": "TEXT",
        "data_origin": "TEXT NOT NULL DEFAULT 'legacy_unknown'",
    }
    for name, definition in reward_additions.items():
        if name not in reward_columns:
            database.execute(f"ALTER TABLE reward_events ADD COLUMN {name} {definition}")
    database.execute(
        """UPDATE reward_events SET signed_amount = COALESCE(signed_amount, points),
           source_activity_id = COALESCE(source_activity_id, report_id),
           audit_reference = COALESCE(audit_reference, 'legacy:' || id)
           WHERE signed_amount IS NULL OR source_activity_id IS NULL OR audit_reference IS NULL"""
    )
    database.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_reward_activity_key
           ON reward_events(activity_key)
           WHERE transaction_type IN ('report_award', 'recycling_award')
             AND activity_key IS NOT NULL"""
    )
    database.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_reward_recycling_action
           ON reward_events(recycling_action_id) WHERE recycling_action_id IS NOT NULL"""
    )
    database.execute(
        "CREATE INDEX IF NOT EXISTS idx_reward_eligible ON reward_events(user_id, e_merit_classification, created_at)"
    )
    database.executescript(
        """CREATE TRIGGER IF NOT EXISTS trg_recycling_action_evidence_immutable
           BEFORE UPDATE OF analysis_id, original_photo, confirmed_waste_json,
             recycling_point_id, proof_photo, proof_latitude, proof_longitude,
             proof_location, proof_location_source, activity_key, activity_affiliation,
             user_id ON recycling_actions
           WHEN OLD.verification_status != 'pending'
           BEGIN
             SELECT RAISE(ABORT, 'reviewed recycling evidence is immutable');
           END;
           CREATE TRIGGER IF NOT EXISTS trg_recycling_action_point_insert
           BEFORE INSERT ON recycling_actions
           BEGIN
             SELECT CASE WHEN NOT EXISTS (
               SELECT 1 FROM recycling_points p WHERE p.id = NEW.recycling_point_id
                 AND p.active = 1 AND p.data_origin = NEW.data_origin)
               THEN RAISE(ABORT, 'active recycling point with matching origin required') END;
           END;
           CREATE TRIGGER IF NOT EXISTS trg_reward_award_insert
           BEFORE INSERT ON reward_events
           WHEN NEW.transaction_type IN ('report_award', 'recycling_award')
           BEGIN
             SELECT CASE WHEN NEW.signed_amount <= 0 OR NEW.points != NEW.signed_amount
                 OR NEW.activity_key IS NULL OR NEW.audit_reference IS NULL
                 OR (NEW.transaction_type = 'report_award' AND NEW.signed_amount != 2)
                 OR (NEW.transaction_type = 'recycling_award' AND NEW.signed_amount != 5)
               THEN RAISE(ABORT, 'invalid activity award') END;
             SELECT CASE WHEN NEW.transaction_type = 'report_award' AND NOT EXISTS (
               SELECT 1 FROM reports r WHERE r.id = NEW.report_id AND r.user_id = NEW.user_id
                 AND r.activity_key = NEW.activity_key AND r.validation_status = 'valid'
                 AND NEW.source_activity_type = 'report' AND NEW.source_activity_id = r.id
                 AND NEW.activity_affiliation = r.activity_affiliation
                 AND NEW.data_origin = r.data_origin)
               THEN RAISE(ABORT, 'report award source mismatch') END;
             SELECT CASE WHEN NEW.transaction_type = 'recycling_award' AND NOT EXISTS (
               SELECT 1 FROM recycling_actions a WHERE a.id = NEW.recycling_action_id
                 AND a.user_id = NEW.user_id AND a.activity_key = NEW.activity_key
                 AND a.verification_status = 'verified'
                 AND NEW.source_activity_type = 'recycling_action'
                 AND NEW.source_activity_id = a.id
                 AND NEW.activity_affiliation = a.activity_affiliation
                 AND NEW.data_origin = a.data_origin)
               THEN RAISE(ABORT, 'recycling award source mismatch') END;
             SELECT CASE WHEN NEW.e_merit_classification = 'eligible_student'
                 AND (NEW.activity_affiliation != 'student' OR NEW.data_origin != 'production')
               THEN RAISE(ABORT, 'ineligible activity') END;
           END;"""
    )


def _ensure_waste_detection_storage(database: sqlite3.Connection) -> None:
    """Allow one child table to store both YOLO and VLM observations."""

    columns = {
        row["name"]: row
        for row in database.execute("PRAGMA table_info(waste_detections)")
    }
    nullable_fields = ("confidence", "x1", "y1", "x2", "y2")
    needs_rebuild = "source" not in columns or any(
        columns[field]["notnull"] for field in nullable_fields
    )
    if not needs_rebuild:
        return

    database.execute("DROP INDEX IF EXISTS idx_waste_detections_report_id")
    database.execute(
        "ALTER TABLE waste_detections RENAME TO waste_detections_legacy"
    )
    database.execute(
        """
        CREATE TABLE waste_detections (
            id TEXT PRIMARY KEY,
            report_id TEXT NOT NULL,
            class_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            waste_category TEXT NOT NULL,
            material TEXT NOT NULL,
            confidence REAL,
            x1 REAL,
            y1 REAL,
            x2 REAL,
            y2 REAL,
            source TEXT NOT NULL DEFAULT 'yolo',
            created_at TEXT NOT NULL,
            FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
        )
        """
    )
    legacy_columns = {
        row["name"]
        for row in database.execute("PRAGMA table_info(waste_detections_legacy)")
    }
    source_expression = "source" if "source" in legacy_columns else "'yolo'"
    database.execute(
        f"""
        INSERT INTO waste_detections (
            id, report_id, class_name, display_name, waste_category,
            material, confidence, x1, y1, x2, y2, source, created_at
        )
        SELECT
            id, report_id, class_name, display_name, waste_category,
            material, confidence, x1, y1, x2, y2,
            {source_expression}, created_at
        FROM waste_detections_legacy
        """
    )
    database.execute("DROP TABLE waste_detections_legacy")
    database.execute(
        "CREATE INDEX idx_waste_detections_report_id "
        "ON waste_detections(report_id)"
    )


def create_analysis_draft(
    *,
    original_image_path: str | Path,
    annotated_image_path: str | Path,
    detection: Mapping[str, Any],
    report: Mapping[str, Any] | None,
    user_id: str,
) -> str:
    """Persist the server-owned result of analysis without creating a report."""
    draft_id = uuid4().hex
    with _connect() as database:
        initialize_database(database)
        database.execute(
            """
            INSERT INTO analysis_drafts (
                id, user_id, original_image_path, annotated_image_path,
                detection_json, ai_report_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                user_id,
                str(Path(original_image_path).resolve()),
                str(Path(annotated_image_path).resolve()),
                json.dumps(detection, ensure_ascii=True),
                json.dumps(report, ensure_ascii=True),
                _utc_now(),
            ),
        )
    return draft_id


def analysis_draft_asset_belongs_to_user(
    user_id: str,
    asset_path: str | Path,
) -> bool:
    """Return whether a temporary AI asset belongs to the given user."""

    resolved_asset_path = str(Path(asset_path).resolve())
    with _connect() as database:
        initialize_database(database)
        row = database.execute(
            """
            SELECT 1
            FROM analysis_drafts
            WHERE user_id = ?
              AND (
                original_image_path = ?
                OR annotated_image_path = ?
              )
            LIMIT 1
            """,
            (user_id, resolved_asset_path, resolved_asset_path),
        ).fetchone()
    return row is not None


def analysis_draft_provider(draft_id: str) -> str | None:
    """Read provider metadata without modifying a historical or active draft."""
    with _connect() as database:
        initialize_database(database)
        row = database.execute(
            "SELECT detection_json FROM analysis_drafts WHERE id = ?", (draft_id,)
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["detection_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    return payload.get("provider") if isinstance(payload, dict) else None


def validate_review_for_drafting(
    analysis_id: str | None, user_id: str, submission: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Authorize a draft and keep model observations separate from user edits."""
    if analysis_id is None:
        return _build_review_confirmation(None, submission)
    with _connect() as database:
        initialize_database(database)
        draft = database.execute(
            "SELECT user_id, consumed_at, detection_json FROM analysis_drafts WHERE id = ?",
            (analysis_id,),
        ).fetchone()
    if draft is None:
        raise DraftNotFoundError("The analysis draft does not exist.")
    if draft["user_id"] != user_id:
        raise DraftAccessDeniedError("This analysis draft does not belong to the authenticated user.")
    if draft["consumed_at"] is not None:
        raise DraftAlreadySubmittedError("This analysis draft has already been submitted.")
    if json.loads(draft["detection_json"]).get("provider") != "florence2":
        raise ReviewValidationError("Report drafting requires Florence or manual items.")
    return _build_review_confirmation(draft["detection_json"], submission)


def _asset_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"


def _deserialize_detections(detection_json: str) -> list[dict[str, Any]]:
    payload = json.loads(detection_json)
    detections = payload.get("detections") if isinstance(payload, dict) else None
    if not isinstance(detections, list):
        raise ValueError("Detection data does not contain a detections list.")
    return detections


def _build_review_confirmation(
    detection_json: str | None,
    submission: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Join review state to immutable detector IDs and derive rule provenance.

    Every raw detection must receive one disposition. Only reportable
    entries become final disposal items; background, removed, and attached cap
    detections remain in the correction audit without inflating item counts.
    """
    payload = json.loads(detection_json) if detection_json is not None else {"provider": "manual", "raw_detections": []}
    if not isinstance(payload, dict) or payload.get("provider") not in {"florence2", "manual"}:
        return None
    raw = payload.get("raw_detections")
    reviews = submission.get("reviewed_detections")
    confirmed = submission.get("confirmed_items")
    if payload.get("provider") == "manual" and reviews is None:
        return None
    if not isinstance(raw, list) or not isinstance(reviews, list) or not isinstance(confirmed, list):
        raise ReviewValidationError("Reports with item review require a complete detection review.")
    raw_by_id = {item.get("id"): item for item in raw if isinstance(item, dict)}
    if len(raw_by_id) != len(raw) or not all(isinstance(key, str) for key in raw_by_id):
        raise ReviewValidationError("The saved model detections are invalid.")
    review_ids: set[str] = set()
    seen_detection_ids: set[str] = set()
    corrections: list[dict[str, Any]] = []
    waste_reviews: dict[str, dict[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("id"), str):
            raise ReviewValidationError("A reviewed item is invalid.")
        review_id = review["id"]
        if review_id in review_ids:
            raise ReviewValidationError("A reviewed item was repeated.")
        review_ids.add(review_id)
        source_id = review.get("source_detection_id")
        if source_id is not None:
            if source_id not in raw_by_id or source_id in seen_detection_ids:
                raise ReviewValidationError("A reviewed detection is missing or repeated.")
            seen_detection_ids.add(source_id)
        elif review.get("disposition") not in {"waste", "needs_confirmation"}:
            raise ReviewValidationError("A manually added item must be reportable waste.")
        disposition = review.get("disposition")
        if disposition not in {"waste", "needs_confirmation", "background", "removed", "attached_component"}:
            raise ReviewValidationError("Each detection needs a valid disposition.")
        corrected_label = str(review.get("corrected_label") or "").strip()
        raw_label = raw_by_id[source_id]["label"] if source_id is not None else None
        effective_label = corrected_label or raw_label or ""
        is_cap = effective_label.casefold().replace("_", " ").strip() in {"cap", "bottle cap", "plastic bottle cap"}
        relation = review.get("component_relation")
        if disposition == "attached_component":
            if not is_cap or relation != "attached":
                raise ReviewValidationError("Only a confirmed attached cap can be excluded as a component.")
        if disposition in {"waste", "needs_confirmation"}:
            if not corrected_label:
                raise ReviewValidationError("Each report item needs an observed label.")
            if is_cap and relation != "detached" and disposition == "waste":
                raise ReviewValidationError("Confirm whether a cap is detached before counting it separately.")
            waste_reviews[review_id] = review
        corrections.append({
            "review_id": review_id,
            "source_detection_id": source_id,
            "original_label": raw_label,
            "corrected_label": corrected_label or None,
            "disposition": disposition,
            "component_relation": relation,
            "material": review.get("material"),
            "category": review.get("category"),
            "quantity": review.get("quantity"),
            "condition_answers": review.get("condition_answers") or {},
        })
    if seen_detection_ids != set(raw_by_id):
        raise ReviewValidationError("Every model detection must be reviewed exactly once.")
    confirmed_by_review = {item.get("review_id"): item for item in confirmed if isinstance(item, dict)}
    split_ids = submission.get("split_recycling_review_ids") or []
    if not isinstance(split_ids, list) or len(split_ids) != len(set(split_ids)):
        raise ReviewValidationError("Split recycling items were repeated.")
    split_set = set(split_ids)
    if (len(confirmed_by_review) != len(confirmed)
            or set(confirmed_by_review) & split_set
            or set(confirmed_by_review) | split_set != set(waste_reviews)):
        raise ReviewValidationError("Confirmed items do not match the detection review.")
    if any(waste_reviews[review_id].get("category") != "Recyclable Waste" for review_id in split_set):
        raise ReviewValidationError("Only recyclable items may be assigned to recycling.")
    final_items: list[dict[str, Any]] = []
    applied_rules: list[dict[str, Any]] = []
    for item in confirmed:
        review = waste_reviews[item["review_id"]]
        source_id = review.get("source_detection_id")
        original = raw_by_id.get(source_id) if source_id else None
        if (item["name"].strip() != review["corrected_label"].strip()
                or item["category"] != review["category"]
                or item.get("material") != review.get("material")
                or item.get("quantity") != review.get("quantity")
                or (item.get("condition_answers") or {}) != (review.get("condition_answers") or {})):
            raise ReviewValidationError("Confirmed item details do not match the reviewed correction.")
        confirmed_material = item.get("material")
        edited = (original is None or original.get("name") != classify_item(item["name"])["canonical_name"]
                  or confirmed_material != original.get("material") or item["category"] != original.get("suggested_category")
                  or bool(item.get("condition_answers")) or item.get("quantity") is not None)
        verdict = classify_item(
            item["name"],
            confirmed_material=confirmed_material if confirmed_material != "Unknown" else None,
            answers=item.get("condition_answers") or {},
            user_confirmed=edited,
        )
        visual_category = (original.get("suggested_category") if original and original.get("classification_source") == "vision" and not edited else None)
        if item["category"] == "Bulky Waste" and verdict["category"] != "Bulky Waste" and visual_category != "Bulky Waste":
            raise ReviewValidationError("Confirm that furniture is discarded waste before reporting it.")
        if item["category"] is not None and verdict["category"] is not None and verdict["category"] != item["category"]:
            raise ReviewValidationError("A confirmed category conflicts with its applied waste rule.")
        if verdict["category"] is None and item["category"] is not None and visual_category != item["category"] and not edited:
            raise ReviewValidationError("An automatic category must match the saved visual assessment.")
        final_items.append({
            **item,
            "source_detection_ids": [review["source_detection_id"]] if review.get("source_detection_id") else [],
            "rule_id": verdict["rule_id"],
            "classification_source": "vision" if visual_category else verdict["classification_source"],
            "uncertainty_reason": original.get("confirmation_reason") if original and original.get("needs_confirmation") else None,
            "classification_state": "needs_confirmation" if item["category"] is None else "classified",
            "independently_verified": False,
            "station_material_key": verdict["station_material_key"],
            "rule_category": verdict["category"],
            "bulky": verdict["bulky"],
            "quantity": item.get("quantity"),
        })
        applied_rules.append({
            "review_id": item["review_id"],
            "rule_id": verdict["rule_id"],
            "classification_source": "vision" if visual_category else verdict["classification_source"],
            "rule_category": verdict["category"],
            "confirmed_category": item["category"],
            "needs_confirmation_at_detection": verdict["needs_confirmation"],
        })
    return {
        "user_corrections": corrections,
        "final_confirmed_items": final_items,
        "applied_classification_rules": applied_rules,
        "split_recycling_review_ids": sorted(split_set),
    }


def _deserialize_ai_analysis(
    detection_json: str,
) -> tuple[list[str], dict[str, Any] | None]:
    """Read immutable hybrid facts from a server-owned analysis draft."""

    payload = json.loads(detection_json)
    if not isinstance(payload, dict):
        return [], None
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return [], None
    raw_categories = analysis.get("categories_detected")
    final_categories = (
        list(dict.fromkeys(raw_categories))
        if isinstance(raw_categories, list)
        and all(isinstance(category, str) for category in raw_categories)
        else []
    )
    raw_yolo = payload.get("raw_yolo")
    raw_vlm = payload.get("raw_vlm")
    metadata = {
        "mode": analysis.get("mode"),
        "provider": analysis.get("provider"),
        "model_id": analysis.get("model_id"),
        "model_revision": analysis.get("model_revision"),
          "visual_model_id": analysis.get("visual_model_id"),
        "service_analysis_id": payload.get("service_analysis_id"),
        "raw_detections": payload.get("raw_detections") if analysis.get("provider") == "florence2" else None,
        "model_detections": payload.get("model_detections") if analysis.get("provider") == "florence2" else None,
        "scene_description": (
            raw_vlm.get("scene_description")
            if isinstance(raw_vlm, dict)
            else None
        ),
        "yolo_available": (
            raw_yolo.get("available")
            if isinstance(raw_yolo, dict)
            else None
        ),
        "vlm_available": (
            raw_vlm.get("available")
            if isinstance(raw_vlm, dict)
            else None
        ),
        "yolo_error": (
            raw_yolo.get("error") if isinstance(raw_yolo, dict) else None
        ),
        "vlm_error": (
            raw_vlm.get("error") if isinstance(raw_vlm, dict) else None
        ),
    }
    return final_categories, metadata


def _insert_detection_rows(
    database: sqlite3.Connection,
    *,
    report_id: str,
    detections: list[dict[str, Any]],
    created_at: str,
) -> None:
    rows: list[tuple[Any, ...]] = []
    for detection in detections:
        bounding_box = detection.get("bounding_box")
        if bounding_box is None:
            coordinates: tuple[float | None, ...] = (None, None, None, None)
        else:
            coordinates = (
                float(bounding_box["x1"]),
                float(bounding_box["y1"]),
                float(bounding_box["x2"]),
                float(bounding_box["y2"]),
            )
        confidence = detection.get("confidence")
        source = detection.get("source", "yolo")
        if source not in {"yolo", "vlm", "yolo+vlm", "florence2"}:
            raise ValueError("Detection source is not supported.")
        rows.append(
            (
                uuid4().hex,
                report_id,
                detection["class_name"],
                detection["display_name"],
                detection["waste_category"],
                detection["material"],
                float(confidence) if confidence is not None else None,
                *coordinates,
                source,
                created_at,
            )
        )

    database.executemany(
        """
        INSERT INTO waste_detections (
            id, report_id, class_name, display_name, waste_category,
            material, confidence, x1, y1, x2, y2, source, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _migrate_legacy_report_detections(database: sqlite3.Connection) -> None:
    """Move legacy report JSON into child rows without duplicating its data."""
    report_columns = {
        row["name"] for row in database.execute("PRAGMA table_info(reports)")
    }
    if "detection_json" not in report_columns:
        return

    legacy_reports = database.execute(
        """
        SELECT id, detection_json, created_at
        FROM reports
        WHERE detection_json IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM waste_detections
              WHERE waste_detections.report_id = reports.id
          )
        """
    ).fetchall()
    for report in legacy_reports:
        try:
            detections = _deserialize_detections(report["detection_json"])
            _insert_detection_rows(
                database,
                report_id=report["id"],
                detections=detections,
                created_at=report["created_at"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        database.execute(
            "UPDATE reports SET detection_json = NULL WHERE id = ?",
            (report["id"],),
        )


def _persist_draft_assets(
    draft: sqlite3.Row,
    report_id: str,
) -> tuple[str, str, Path]:
    original_source = Path(draft["original_image_path"])
    annotated_source = Path(draft["annotated_image_path"])
    if not original_source.is_file() or not annotated_source.is_file():
        raise DraftAssetError("One or more draft images are no longer available.")

    report_directory = REPORT_ASSETS_DIR / report_id
    report_directory.mkdir(parents=True, exist_ok=False)
    original_name = f"original{_asset_suffix(original_source)}"
    annotated_name = f"annotated{_asset_suffix(annotated_source)}"
    shutil.copy2(original_source, report_directory / original_name)
    shutil.copy2(annotated_source, report_directory / annotated_name)

    base_url = f"{REPORT_ASSET_URL_PREFIX}/{report_id}"
    return (
        f"{base_url}/{original_name}",
        f"{base_url}/{annotated_name}",
        report_directory,
    )


def _persist_uploaded_image(
    source: Path,
    report_id: str,
) -> tuple[str, Path]:
    if not source.is_file():
        raise DraftAssetError("The uploaded report image is no longer available.")

    report_directory = REPORT_ASSETS_DIR / report_id
    report_directory.mkdir(parents=True, exist_ok=False)
    original_name = f"original{_asset_suffix(source)}"
    shutil.copy2(source, report_directory / original_name)
    return (
        f"{REPORT_ASSET_URL_PREFIX}/{report_id}/{original_name}",
        report_directory,
    )


def create_report(submission: Mapping[str, Any]) -> dict[str, str]:
    """Create one permanent report and consume its analysis draft atomically."""
    report_id = uuid4().hex
    now = _utc_now()
    reference = f"SCA-{datetime.now(timezone.utc):%y%m%d}-{report_id[:6].upper()}"
    report_directory: Path | None = None
    draft_sources: tuple[Path, Path] | None = None
    database = _connect()

    try:
        initialize_database(database)
        database.execute("BEGIN IMMEDIATE")

        analysis_id = submission.get("analysis_id")
        original_image: str | None = None
        annotated_image: str | None = None
        detections: list[dict[str, Any]] = []
        final_categories: list[str] = []
        ai_analysis: dict[str, Any] | None = None
        confirmation: dict[str, Any] | None = None
        source_photo: Path | None = None
        if analysis_id:
            draft = database.execute(
                "SELECT * FROM analysis_drafts WHERE id = ?",
                (analysis_id,),
            ).fetchone()
            if draft is None:
                raise DraftNotFoundError("The analysis draft does not exist.")
            if draft["consumed_at"] is not None:
                raise DraftAlreadySubmittedError(
                    "This analysis draft has already been submitted."
                )
            if (
                submission.get("reporter_role") != "user"
                or not submission.get("user_id")
                or draft["user_id"] != submission.get("user_id")
            ):
                raise DraftAccessDeniedError(
                    "This analysis draft does not belong to the authenticated user."
                )
            confirmation = _build_review_confirmation(
                draft["detection_json"], submission,
            )
            draft_sources = (
                Path(draft["original_image_path"]),
                Path(draft["annotated_image_path"]),
            )
            source_photo = draft_sources[0]
            original_image, annotated_image, report_directory = _persist_draft_assets(
                draft,
                report_id,
            )
            detections = _deserialize_detections(draft["detection_json"])
            final_categories, ai_analysis = _deserialize_ai_analysis(
                draft["detection_json"]
            )
        elif uploaded_image_path := submission.get("uploaded_image_path"):
            source_photo = Path(uploaded_image_path)
            original_image, report_directory = _persist_uploaded_image(
                Path(uploaded_image_path),
                report_id,
            )
            confirmation = _build_review_confirmation(None, submission)

        confirmed_items = submission.get("confirmed_items")
        if confirmed_items:
            final_categories = list(dict.fromkeys(
                item["category"] for item in confirmed_items if item["category"] is not None
            ))

        activity_key = (
            "sha256:" + hashlib.sha256(source_photo.read_bytes()).hexdigest()
            if source_photo is not None else f"report:{report_id}"
        )
        split_recycling_ids = confirmation.get("split_recycling_review_ids", []) if confirmation else []
        if split_recycling_ids:
            activity_key += ":report"

        database.execute(
            """
            INSERT INTO reports (
                id, reference, analysis_id, reporter_role, user_id,
                guest_name, guest_email, original_image, annotated_image,
                title, summary, waste_identified, recommended_action,
                environmental_concern, category, final_categories_json,
                ai_analysis_json, location, latitude, longitude,
                location_address, location_street, location_city, location_state,
                location_postcode, location_country, location_source, site_notes,
                status, validation_status, activity_affiliation, activity_key,
                confirmed_ai_result_json, data_origin, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                report_id,
                reference,
                analysis_id,
                submission["reporter_role"],
                submission.get("user_id"),
                submission.get("guest_name"),
                submission.get("guest_email"),
                original_image,
                annotated_image,
                submission["title"],
                submission["summary"],
                submission.get("waste_identified", ""),
                submission.get("recommended_action", ""),
                submission.get("environmental_concern", ""),
                submission["category"],
                json.dumps(final_categories, ensure_ascii=True),
                (
                    json.dumps(ai_analysis, ensure_ascii=True)
                    if ai_analysis is not None
                    else None
                ),
                submission["location"],
                submission["latitude"],
                submission["longitude"],
                submission.get("location_address"),
                submission.get("location_street"),
                submission.get("location_city"),
                submission.get("location_state"),
                submission.get("location_postcode"),
                submission.get("location_country"),
                submission["location_source"],
                submission.get("site_notes", ""),
                "submitted",
                "pending",
                submission.get("activity_affiliation", "unknown"),
                activity_key,
                json.dumps({
                    "analysis": ai_analysis,
                    "rule_version": submission.get("rule_version"),
                    "final_categories": final_categories,
                    "category": submission["category"],
                    "waste_identified": submission.get("waste_identified", ""),
                    "recommended_action": submission.get("recommended_action", ""),
                    "items": confirmed_items or [],
                    "draft_source": submission.get("draft_source", "user"),
                    "draft_model_id": submission.get("draft_model_id"),
                    "user_edited_fields": submission.get("user_edited_fields", []),
                    "submitted_by_user": True,
                    "independently_verified": False,
                    **(confirmation or {}),
                }, ensure_ascii=True),
                "production",
                now,
                now,
            ),
        )
        database.execute(
            "UPDATE reports SET location_address_source = ? WHERE id = ?",
            (submission.get("location_address_source"), report_id),
        )
        _insert_detection_rows(
            database,
            report_id=report_id,
            detections=detections,
            created_at=now,
        )
        if analysis_id:
            database.execute(
                "UPDATE analysis_drafts SET consumed_at = ?, split_recycling_ids_json = ? WHERE id = ?",
                (now, json.dumps(split_recycling_ids) if split_recycling_ids else None, analysis_id),
            )
        database.execute(
            """INSERT INTO report_status_events
               (id, report_id, actor_id, previous_status, new_status, created_at)
               VALUES (?, ?, ?, '', 'submitted', ?)""",
            (uuid4().hex, report_id, submission.get("user_id") or "guest", now),
        )
        database.commit()
    except Exception:
        database.rollback()
        if report_directory is not None:
            shutil.rmtree(report_directory, ignore_errors=True)
        raise
    finally:
        database.close()

    if draft_sources is not None and not split_recycling_ids:
        for source in draft_sources:
            try:
                source.unlink(missing_ok=True)
            except OSError:
                pass

    return {
        "id": report_id,
        "reference": reference,
        "status": "submitted",
        "submitted_at": now,
        "original_image": original_image or "",
        "annotated_image": annotated_image or "",
    }


def list_reports() -> list[dict[str, Any]]:
    """Return persisted reports for the existing administrative report list."""
    with _connect() as database:
        initialize_database(database)
        rows = database.execute(
            """
            SELECT
                reports.*,
                MAX(waste_detections.confidence) AS max_confidence
            FROM reports
            LEFT JOIN waste_detections
                ON waste_detections.report_id = reports.id
            GROUP BY reports.id
            ORDER BY reports.created_at DESC
            """
        ).fetchall()

    return [
        {
            "id": row["id"],
            "reference": row["reference"],
            "category": row["category"],
            "location": row["location"],
            "submitted_at": row["created_at"],
            "status": row["status"],
            "confidence": (
                round(float(row["max_confidence"]) * 100)
                if row["max_confidence"] is not None else None
            ),
            "description": row["summary"],
            "reporter": (
                row["user_id"]
                if row["reporter_role"] == "user"
                else row["guest_name"] or "Guest reporter"
            ),
            "reporter_role": row["reporter_role"],
            "validation_status": row["validation_status"],
        }
        for row in rows
    ]


def get_report(report_id: str) -> dict[str, Any] | None:
    """Return one persisted report with all associated AI detections."""
    with _connect() as database:
        initialize_database(database)
        report = database.execute(
            "SELECT * FROM reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if report is None:
            return None
        detections = database.execute(
            """
            SELECT * FROM waste_detections
            WHERE report_id = ?
            ORDER BY confidence DESC, class_name
            """,
            (report_id,),
        ).fetchall()
        reward_points = database.execute(
            "SELECT COALESCE(SUM(points), 0) FROM reward_events WHERE report_id = ?",
            (report_id,),
        ).fetchone()[0]
        generated_report = None
        if report["analysis_id"]:
            draft = database.execute(
                "SELECT ai_report_json FROM analysis_drafts WHERE id = ?",
                (report["analysis_id"],),
            ).fetchone()
            if draft is not None:
                try:
                    candidate = json.loads(draft["ai_report_json"])
                except (json.JSONDecodeError, TypeError):
                    candidate = None
                report_fields = (
                    "title",
                    "summary",
                    "waste_identified",
                    "recommended_action",
                    "environmental_concern",
                )
                if isinstance(candidate, dict) and all(
                    isinstance(candidate.get(field), str) for field in report_fields
                ):
                    generated_report = {
                        field: candidate[field] for field in report_fields
                    }
        try:
            stored_categories = json.loads(report["final_categories_json"])
        except (json.JSONDecodeError, TypeError):
            stored_categories = []
        final_categories = (
            stored_categories
            if isinstance(stored_categories, list)
            and all(isinstance(category, str) for category in stored_categories)
            else []
        )
        try:
            stored_ai_analysis = json.loads(report["ai_analysis_json"])
        except (json.JSONDecodeError, TypeError):
            stored_ai_analysis = None
        ai_analysis = (
            stored_ai_analysis if isinstance(stored_ai_analysis, dict) else None
        )
        try:
            confirmed_results = json.loads(report["confirmed_ai_result_json"])
        except (json.JSONDecodeError, TypeError):
            confirmed_results = None
        report_items = (confirmed_results.get("final_confirmed_items") or confirmed_results.get("items") or []) if isinstance(confirmed_results, dict) else []
        grouped_report_items = group_report_observations(report_items) if isinstance(report_items, list) else []
        status_events = database.execute(
            """SELECT previous_status, new_status, reason, assigned_team,
                      resolution_details, after_photo, created_at
               FROM report_status_events WHERE report_id = ? ORDER BY created_at, rowid""",
            (report_id,),
        ).fetchall()

    return {
        "id": report["id"],
        "reference": report["reference"],
        "category": report["category"],
        "location": report["location"],
        "latitude": report["latitude"],
        "longitude": report["longitude"],
        "location_address": report["location_address"],
        "location_address_source": report["location_address_source"],
        "location_street": report["location_street"],
        "location_city": report["location_city"],
        "location_state": report["location_state"],
        "location_postcode": report["location_postcode"],
        "location_country": report["location_country"],
        "location_source": report["location_source"],
        "site_notes": report["site_notes"],
        "status": report["status"],
        "assigned_team": report["assigned_team"],
        "resolution_details": report["resolution_details"],
        "after_photo": report["after_photo"],
        "status_events": [dict(event) for event in status_events],
        "validation_status": report["validation_status"],
        "reward_points": int(reward_points),
        "validated_at": report["validated_at"],
        "reporter_role": report["reporter_role"],
        "reporter": (
            report["user_id"]
            if report["reporter_role"] == "user"
            else report["guest_name"] or "Guest reporter"
        ),
        "title": report["title"],
        "summary": report["summary"],
        "waste_identified": report["waste_identified"],
        "recommended_action": report["recommended_action"],
        "environmental_concern": report["environmental_concern"],
        "generated_report": generated_report,
        "final_categories": final_categories,
        "ai_analysis": ai_analysis,
        "confirmed_results": confirmed_results,
        "grouped_report_items": grouped_report_items,
        "original_image": report["original_image"] or "",
        "annotated_image": report["annotated_image"] or "",
        "created_at": report["created_at"],
        "updated_at": report["updated_at"],
        "detections": [
            {
                "id": detection["id"],
                "class_name": detection["class_name"],
                "display_name": detection["display_name"],
                "waste_category": detection["waste_category"],
                "material": detection["material"],
                "confidence": detection["confidence"],
                "x1": detection["x1"],
                "y1": detection["y1"],
                "x2": detection["x2"],
                "y2": detection["y2"],
                "source": detection["source"],
                "created_at": detection["created_at"],
            }
            for detection in detections
        ],
    }


def get_member_dashboard(user_id: str, *, report_limit: int = 5) -> dict[str, Any]:
    """Return reward totals, rank, and recent reports for one member."""
    if report_limit <= 0:
        raise ValueError("Report limit must be positive.")

    with _connect() as database:
        initialize_database(database)
        statistics = database.execute(
            """
            WITH member_totals AS (
                SELECT
                    user_id,
                    SUM(points) AS points,
                    SUM(CASE WHEN transaction_type = 'report_award' THEN 1 ELSE 0 END) AS valid_reports
                FROM reward_events
                WHERE data_origin != 'demo'
                GROUP BY user_id
            ),
            current_member AS (
                SELECT
                    COALESCE(
                        (SELECT points FROM member_totals WHERE user_id = ?),
                        0
                    ) AS points,
                    COALESCE(
                        (SELECT valid_reports FROM member_totals WHERE user_id = ?),
                        0
                    ) AS valid_reports
            )
            SELECT
                points,
                valid_reports,
                CASE
                    WHEN points = 0 THEN NULL
                    ELSE 1 + (
                        SELECT COUNT(*)
                        FROM member_totals
                        WHERE member_totals.points > current_member.points
                    )
                END AS rank
            FROM current_member
            """,
            (user_id, user_id),
        ).fetchone()
        earned_rank = database.execute("""
            WITH earned AS (
              SELECT e.user_id, SUM(e.signed_amount) AS lifetime_points
              FROM reward_events e JOIN public_participants p ON p.user_id = e.user_id
              WHERE (e.transaction_type IN ('report_award', 'recycling_award') OR e.reason = 'split_incident_cap_offset')
                AND e.data_origin = 'production'
                AND p.role = 'user' AND p.visible = 1 AND p.disabled = 0 AND p.deleted = 0
                AND p.data_origin = 'production'
              GROUP BY e.user_id
            )
            SELECT CASE WHEN mine.lifetime_points IS NULL THEN NULL ELSE
              1 + (SELECT COUNT(*) FROM earned others WHERE others.lifetime_points > mine.lifetime_points) END AS rank
            FROM (SELECT (SELECT lifetime_points FROM earned WHERE user_id = ?) AS lifetime_points) mine
        """, (user_id,)).fetchone()
        reports = database.execute(
            """
            SELECT
                id,
                reference,
                COALESCE(NULLIF(trim(location), ''), 'Location not recorded') AS location,
                CASE WHEN status IS NULL OR status IN ('pending', '') THEN 'submitted' ELSE status END AS status,
                COALESCE(NULLIF(validation_status, ''), 'pending') AS validation_status,
                COALESCE(created_at, updated_at) AS created_at
            FROM reports
            WHERE reporter_role = 'user' AND user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, report_limit),
        ).fetchall()

    return {
        "points": int(statistics["points"]),
        "valid_reports": int(statistics["valid_reports"]),
        "rank": int(earned_rank["rank"]) if earned_rank["rank"] is not None else None,
        "reports": [
            {
                "id": report["id"],
                "reference": report["reference"],
                "location": report["location"],
                "status": report["status"],
                "validation_status": report["validation_status"],
                "submitted_at": report["created_at"],
            }
            for report in reports
        ],
    }


def get_own_report_tracking(report_id: str, user_id: str) -> dict[str, Any] | None:
    """Return one resident's report and municipal status history only to its owner."""
    with _connect() as database:
        initialize_database(database)
        row = database.execute(
            """SELECT id, reference, title, location, category, status, validation_status,
                      rejection_reason, assigned_team, resolution_details, created_at, updated_at
               FROM reports WHERE id = ? AND user_id = ? AND reporter_role = 'user'""",
            (report_id, user_id),
        ).fetchone()
        if row is None:
            return None
        events = database.execute(
            """SELECT previous_status, new_status, reason, assigned_team,
                      resolution_details, created_at FROM report_status_events
               WHERE report_id = ? ORDER BY created_at, rowid""",
            (report_id,),
        ).fetchall()
        return dict(row) | {"status_events": [dict(event) for event in events]}


def register_public_participant(user_id: str, role: str, email: str = "") -> None:
    """Register a safe public pseudonym; never publish email or matric data."""
    with _connect() as database:
        initialize_database(database)
        domain = email.strip().casefold().rpartition("@")[2]
        origin = "demo" if domain in {"example.com", "example.org", "example.net", "test", "test.local"} else "production"
        existing = database.execute("SELECT 1 FROM public_participants WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            database.execute("UPDATE public_participants SET role = ?, data_origin = ? WHERE user_id = ?", (role, origin, user_id))
            return
        for _ in range(5):
            try:
                database.execute("INSERT INTO public_participants (user_id, public_name, role, data_origin) VALUES (?, ?, ?, ?)",
                                 (user_id, f"Participant {secrets.randbelow(900000) + 100000}", role, origin))
                return
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("A unique public participant name could not be assigned.")


def get_leaderboard(*, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid leaderboard page.")
    with _connect() as database:
        initialize_database(database)
        rows = database.execute("""
            WITH earned AS (
                SELECT user_id, SUM(signed_amount) AS points,
                       SUM(CASE WHEN transaction_type = 'report_award' THEN 1 ELSE 0 END) AS valid_reports
                FROM reward_events
                WHERE (transaction_type IN ('report_award', 'recycling_award') OR reason = 'split_incident_cap_offset')
                  AND data_origin = 'production'
                GROUP BY user_id
            ), ranked AS (
                SELECT p.user_id, p.public_name, e.points, e.valid_reports,
                       RANK() OVER (ORDER BY e.points DESC) AS rank
                FROM earned e JOIN public_participants p ON p.user_id = e.user_id
                WHERE p.role = 'user' AND p.visible = 1 AND p.disabled = 0
                  AND p.deleted = 0 AND p.data_origin = 'production' AND e.points > 0
            )
            SELECT *, (SELECT COUNT(*) FROM ranked) AS total
            FROM ranked ORDER BY points DESC, user_id ASC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        total = database.execute("""SELECT COUNT(DISTINCT e.user_id) FROM reward_events e
            JOIN public_participants p ON p.user_id = e.user_id
            WHERE e.transaction_type IN ('report_award', 'recycling_award') AND e.data_origin = 'production'
              AND p.role = 'user' AND p.visible = 1 AND p.disabled = 0 AND p.deleted = 0
              AND p.data_origin = 'production'""").fetchone()[0]
    return {"entries": [{"id": row["user_id"], "name": row["public_name"],
                         "points": row["points"], "valid_reports": row["valid_reports"],
                         "rank": row["rank"]} for row in rows],
            "total": total, "limit": limit, "offset": offset}


def other_incident_has_award(database: sqlite3.Connection, activity_key: str, analysis_id: str | None) -> bool:
    """Prevent another analysis of the same photo earning a second base reward."""
    base = activity_key.removesuffix(":report").removesuffix(":recycling")
    return database.execute("""
        SELECT 1 FROM reward_events e
        LEFT JOIN reports r ON r.id = e.report_id
        LEFT JOIN recycling_actions a ON a.id = e.recycling_action_id
        WHERE e.transaction_type IN ('report_award', 'recycling_award')
          AND (e.activity_key = ? OR e.activity_key = ? OR e.activity_key = ?)
          AND COALESCE(r.analysis_id, a.analysis_id, '') != COALESCE(?, '')
        LIMIT 1
    """, (base, base + ":report", base + ":recycling", analysis_id)).fetchone() is not None


def validate_report(
    report_id: str, validation_status: str, reviewer_id: str | None = None,
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    """Record a municipal verification decision without issuing campus rewards."""
    if validation_status not in {"valid", "invalid"}:
        raise ValueError("Validation status must be 'valid' or 'invalid'.")
    if validation_status == "invalid" and not (rejection_reason or "").strip():
        raise ValueError("A rejection reason is required.")

    now = _utc_now()
    database = _connect()
    try:
        initialize_database(database)
        database.execute("BEGIN IMMEDIATE")
        report = database.execute(
            """
            SELECT reporter_role, user_id, analysis_id, validation_status, status, activity_affiliation,
                   activity_key, data_origin
            FROM reports
            WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
        if report is None:
            raise ReportNotFoundError("Report not found.")

        current_validation = report["validation_status"]
        if current_validation != "pending":
            if current_validation != validation_status:
                raise ValidationAlreadyDecidedError(
                    "This report already has a final validation decision."
                )
            database.commit()
            return {
                "report_id": report_id,
                "validation_status": current_validation,
                "status": report["status"],
                "reward_awarded": False,
                "reward_points": 0,
            }

        report_status = "verified" if validation_status == "valid" else "rejected"
        database.execute(
            """
            UPDATE reports
            SET validation_status = ?, validated_at = ?, status = ?, updated_at = ?,
                reviewer_id = ?, reviewed_at = ?, rejection_reason = ?,
                activity_key = COALESCE(activity_key, ?)
            WHERE id = ?
            """,
            (validation_status, now, report_status, now, reviewer_id, now,
             rejection_reason if validation_status == "invalid" else None,
             f"report:{report_id}", report_id),
        )

        database.execute(
            """INSERT INTO report_status_events
               (id, report_id, actor_id, previous_status, new_status, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uuid4().hex, report_id, reviewer_id or "municipal-admin", report["status"],
             report_status, rejection_reason.strip() if validation_status == "invalid" else None, now),
        )

        database.commit()
        return {
            "report_id": report_id,
            "validation_status": validation_status,
            "status": report_status,
            "reward_awarded": False,
            "reward_points": 0,
        }
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def transition_report(
    report_id: str, action: str, actor_id: str, *, assigned_team: str = "",
    resolution_details: str = "", after_photo_source: Path | None = None,
) -> dict[str, Any]:
    """Assign or resolve a verified report with an immutable status audit."""
    if action not in {"assign", "resolve"}:
        raise ValueError("Unsupported report action.")
    team = assigned_team.strip()
    details = resolution_details.strip()
    if action == "assign" and (not team or len(team) > 120):
        raise ValueError("Enter the municipal team assigned to this report.")
    if action == "resolve" and (not details or len(details) > 2000):
        raise ValueError("Record resolution details before marking a report resolved.")
    database = _connect()
    copied_photo: Path | None = None
    try:
        initialize_database(database)
        database.execute("BEGIN IMMEDIATE")
        row = database.execute(
            "SELECT status, validation_status, assigned_team FROM reports WHERE id = ?", (report_id,),
        ).fetchone()
        if row is None:
            raise ReportNotFoundError("Report not found.")
        if row["validation_status"] != "valid":
            raise ValidationAlreadyDecidedError("Verify the report before assigning or resolving it.")
        if action == "assign":
            if row["status"] not in {"verified", "in_progress"}:
                raise ValidationAlreadyDecidedError("Only a verified or active report can be assigned.")
            new_status = "in_progress"
        else:
            if row["status"] != "in_progress" or not row["assigned_team"]:
                raise ValidationAlreadyDecidedError("Assign an active report before resolving it.")
            new_status = "resolved"
        now = _utc_now()
        after_photo = None
        if after_photo_source is not None:
            if action != "resolve":
                raise ValueError("An after-photo belongs to a resolution only.")
            destination = REPORT_ASSETS_DIR / report_id
            destination.mkdir(parents=True, exist_ok=True)
            copied_photo = destination / f"after{_asset_suffix(after_photo_source)}"
            if copied_photo.exists():
                raise ValueError("A resolution photo already exists for this report.")
            shutil.copy2(after_photo_source, copied_photo)
            after_photo = f"{REPORT_ASSET_URL_PREFIX}/{report_id}/{copied_photo.name}"
        database.execute(
            """UPDATE reports SET status = ?, assigned_team = COALESCE(?, assigned_team),
               resolution_details = COALESCE(?, resolution_details),
               after_photo = COALESCE(?, after_photo), updated_at = ? WHERE id = ?""",
            (new_status, team if action == "assign" else None,
             details if action == "resolve" else None, after_photo, now, report_id),
        )
        database.execute(
            """INSERT INTO report_status_events
               (id, report_id, actor_id, previous_status, new_status,
                assigned_team, resolution_details, after_photo, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid4().hex, report_id, actor_id, row["status"], new_status,
             team if action == "assign" else None, details if action == "resolve" else None,
             after_photo, now),
        )
        database.commit()
        return {"report_id": report_id, "status": new_status, "assigned_team": team or row["assigned_team"],
                "resolution_details": details or None, "after_photo": after_photo}
    except Exception:
        database.rollback()
        if copied_photo is not None:
            copied_photo.unlink(missing_ok=True)
        raise
    finally:
        database.close()


__all__ = [
    "DATABASE_PATH",
    "REPORT_ASSETS_DIR",
    "DraftAlreadySubmittedError",
    "DraftAccessDeniedError",
    "DraftAssetError",
    "DraftNotFoundError",
    "ReportNotFoundError",
    "ValidationAlreadyDecidedError",
    "analysis_draft_asset_belongs_to_user",
    "create_analysis_draft",
    "create_report",
    "get_member_dashboard",
    "get_own_report_tracking",
    "get_report",
    "initialize_database",
    "list_reports",
    "validate_report",
]
