"""SQLite persistence for analysis drafts and submitted waste reports."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from app.core.config import get_settings


_settings = get_settings()
DATABASE_PATH = _settings.database_path
REPORT_ASSETS_DIR = _settings.report_assets_dir
REPORT_ASSET_URL_PREFIX = "/api/reports/files"
REPORT_VALIDATION_REWARD_POINTS = 40


class DraftNotFoundError(LookupError):
    """Raised when a submitted analysis draft does not exist."""


class DraftAlreadySubmittedError(RuntimeError):
    """Raised when an analysis draft has already created a report."""


class DraftAssetError(RuntimeError):
    """Raised when a draft image is no longer available."""


class DraftAccessDeniedError(PermissionError):
    """Raised when a user attempts to consume another user's AI draft."""


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

            CREATE TABLE IF NOT EXISTS reward_events (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                points INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_reward_events_user_id
                ON reward_events(user_id);
            """
        )
        _ensure_analysis_draft_owner_column(database)
        _ensure_report_validation_columns(database)
        _ensure_report_location_columns(database)
        _ensure_report_ai_columns(database)
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


def _ensure_report_location_columns(database: sqlite3.Connection) -> None:
    """Add structured location fields without invalidating historical reports."""

    columns = {
        row["name"] for row in database.execute("PRAGMA table_info(reports)")
    }
    definitions = {
        "latitude": "REAL",
        "longitude": "REAL",
        "location_address": "TEXT",
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


def _asset_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"


def _deserialize_detections(detection_json: str) -> list[dict[str, Any]]:
    payload = json.loads(detection_json)
    detections = payload.get("detections") if isinstance(payload, dict) else None
    if not isinstance(detections, list):
        raise ValueError("Detection data does not contain a detections list.")
    return detections


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
        if source not in {"yolo", "vlm", "yolo+vlm"}:
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
            draft_sources = (
                Path(draft["original_image_path"]),
                Path(draft["annotated_image_path"]),
            )
            original_image, annotated_image, report_directory = _persist_draft_assets(
                draft,
                report_id,
            )
            detections = _deserialize_detections(draft["detection_json"])
            final_categories, ai_analysis = _deserialize_ai_analysis(
                draft["detection_json"]
            )
        elif uploaded_image_path := submission.get("uploaded_image_path"):
            original_image, report_directory = _persist_uploaded_image(
                Path(uploaded_image_path),
                report_id,
            )

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
                status, validation_status, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                "processing",
                "pending",
                now,
                now,
            ),
        )
        _insert_detection_rows(
            database,
            report_id=report_id,
            detections=detections,
            created_at=now,
        )
        if analysis_id:
            database.execute(
                "UPDATE analysis_drafts SET consumed_at = ? WHERE id = ?",
                (now, analysis_id),
            )
        database.commit()
    except Exception:
        database.rollback()
        if report_directory is not None:
            shutil.rmtree(report_directory, ignore_errors=True)
        raise
    finally:
        database.close()

    if draft_sources is not None:
        for source in draft_sources:
            try:
                source.unlink(missing_ok=True)
            except OSError:
                pass

    return {
        "id": report_id,
        "reference": reference,
        "status": "processing",
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
            "confidence": round(float(row["max_confidence"] or 0) * 100),
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

    return {
        "id": report["id"],
        "reference": report["reference"],
        "category": report["category"],
        "location": report["location"],
        "latitude": report["latitude"],
        "longitude": report["longitude"],
        "location_address": report["location_address"],
        "location_street": report["location_street"],
        "location_city": report["location_city"],
        "location_state": report["location_state"],
        "location_postcode": report["location_postcode"],
        "location_country": report["location_country"],
        "location_source": report["location_source"],
        "site_notes": report["site_notes"],
        "status": report["status"],
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
                    COUNT(*) AS valid_reports
                FROM reward_events
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
        reports = database.execute(
            """
            SELECT
                id,
                reference,
                location,
                status,
                validation_status,
                created_at
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
        "rank": int(statistics["rank"]) if statistics["rank"] is not None else None,
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


def validate_report(report_id: str, validation_status: str) -> dict[str, Any]:
    """Persist one final validation decision and award a member report once."""
    if validation_status not in {"valid", "invalid"}:
        raise ValueError("Validation status must be 'valid' or 'invalid'.")

    now = _utc_now()
    database = _connect()
    try:
        initialize_database(database)
        database.execute("BEGIN IMMEDIATE")
        report = database.execute(
            """
            SELECT reporter_role, user_id, validation_status, status
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

        report_status = "in_progress" if validation_status == "valid" else "completed"
        database.execute(
            """
            UPDATE reports
            SET validation_status = ?, validated_at = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (validation_status, now, report_status, now, report_id),
        )

        reward_awarded = False
        if (
            validation_status == "valid"
            and report["reporter_role"] == "user"
            and report["user_id"]
        ):
            cursor = database.execute(
                """
                INSERT OR IGNORE INTO reward_events (
                    id, report_id, user_id, points, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    report_id,
                    report["user_id"],
                    REPORT_VALIDATION_REWARD_POINTS,
                    "validated_report",
                    now,
                ),
            )
            reward_awarded = cursor.rowcount == 1

        database.commit()
        return {
            "report_id": report_id,
            "validation_status": validation_status,
            "status": report_status,
            "reward_awarded": reward_awarded,
            "reward_points": (
                REPORT_VALIDATION_REWARD_POINTS if reward_awarded else 0
            ),
        }
    except Exception:
        database.rollback()
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
    "get_report",
    "initialize_database",
    "list_reports",
    "validate_report",
]
