"""Database invariants for the incremental campus migration."""

import sqlite3
from pathlib import Path

import pytest

from app.repositories import reports


def _db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def test_existing_reward_is_preserved_without_merit_reclassification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    path = tmp_path / "old.db"
    monkeypatch.setattr(reports, "DATABASE_PATH", path)
    with _db(path) as db:
        reports.initialize_database(db)
        db.execute(
            """INSERT INTO reports (id, reference, reporter_role, user_id, title, summary,
               category, location, status, created_at, updated_at)
               VALUES ('old-report', 'old-ref', 'user', 'student-1', 'Old', 'Old',
               'household', 'Arau', 'completed', '2025-01-01', '2025-01-01')"""
        )
        db.execute("DROP TABLE reward_events")
        db.execute(
            """CREATE TABLE reward_events (
               id TEXT PRIMARY KEY, report_id TEXT NOT NULL UNIQUE, user_id TEXT NOT NULL,
               points INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL,
               activity_affiliation TEXT NOT NULL DEFAULT 'unknown')"""
        )
        db.execute(
            """INSERT INTO reward_events VALUES
               ('old-reward', 'old-report', 'student-1', 40, 'validated_report',
                '2025-01-01', 'student')"""
        )
    with _db(path) as db:
        reports.initialize_database(db)
        reports.initialize_database(db)
        row = db.execute("SELECT * FROM reward_events WHERE id = 'old-reward'").fetchone()
        assert row["points"] == row["signed_amount"] == 40
        assert row["activity_affiliation"] == "student"
        assert row["e_merit_classification"] == "legacy_unclassified"
        assert row["data_origin"] == "legacy_unknown"
        assert db.execute("SELECT data_origin FROM reports WHERE id = 'old-report'").fetchone()[0] == "legacy_unknown"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_same_activity_cannot_earn_report_and_recycling_rewards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    path = tmp_path / "campus.db"
    monkeypatch.setattr(reports, "DATABASE_PATH", path)
    with _db(path) as db:
        reports.initialize_database(db)
        db.execute(
            """INSERT INTO reports (id, reference, reporter_role, user_id, title, summary,
               category, location, status, validation_status, activity_affiliation,
               activity_key, data_origin, created_at, updated_at)
               VALUES ('r1', 'ref1', 'user', 'u1', 'Waste', 'Waste', 'Recyclable Waste',
               'Arau', 'in_progress', 'valid', 'student', 'sha256:one', 'production', 'now', 'now')"""
        )
        db.execute(
            """INSERT INTO recycling_points
               (id, name, latitude, longitude, accepted_materials_json,
                data_origin, created_at, updated_at)
               VALUES ('p1', 'Test point', 0, 0, '["plastic"]', 'demo', 'now', 'now')"""
        )
        db.execute(
            """INSERT INTO recycling_actions
               (id, user_id, original_photo, confirmed_waste_json, recycling_point_id,
                proof_photo, proof_location, activity_key, activity_affiliation,
                verification_status, reviewer_id, reviewed_at, data_origin, created_at, updated_at)
               VALUES ('a1', 'u1', 'original.jpg', '["plastic"]', 'p1', 'proof.jpg',
                'test location', 'sha256:one', 'student', 'verified', 'admin', 'now',
                'demo', 'now', 'now')"""
        )
        db.execute(
            """INSERT INTO reward_events
               (id, report_id, user_id, signed_amount, points, transaction_type,
                source_activity_type, source_activity_id, activity_key, reason,
                activity_affiliation, e_merit_classification, audit_reference,
                data_origin, created_at)
               VALUES ('award1', 'r1', 'u1', 2, 2, 'report_award', 'report', 'r1',
                'sha256:one', 'validated_report', 'student', 'eligible_student',
                'review:r1', 'production', 'now')"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO reward_events
                   (id, recycling_action_id, user_id, signed_amount, points,
                    transaction_type, source_activity_type, source_activity_id,
                    activity_key, reason, activity_affiliation, e_merit_classification,
                    audit_reference, data_origin, created_at)
                   VALUES ('award2', 'a1', 'u1', 5, 5, 'recycling_award',
                    'recycling_action', 'a1', 'sha256:one', 'verified_recycling',
                    'student', 'ineligible_unknown', 'review:a1', 'demo', 'now')"""
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO reward_events
                   (id, recycling_action_id, user_id, signed_amount, points,
                    transaction_type, source_activity_type, source_activity_id,
                    activity_key, reason, activity_affiliation, e_merit_classification,
                    audit_reference, data_origin, created_at)
                   VALUES ('award3', 'a1', 'u1', 4, 4, 'recycling_award',
                    'recycling_action', 'a1', 'sha256:other', 'verified_recycling',
                    'student', 'eligible_student', 'review:a1', 'demo', 'now')"""
            )
