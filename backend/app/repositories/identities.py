"""Local affiliation and matric data, separate from Supabase permissions."""

from __future__ import annotations

import sqlite3
import hashlib
import time
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.core.google_identity import suggested_matric


def _connect() -> sqlite3.Connection:
    path = get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, timeout=10)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    return database


def _initialize(database: sqlite3.Connection) -> None:
    database.execute(
        """CREATE TABLE IF NOT EXISTS member_identities (
            user_id TEXT PRIMARY KEY,
            google_sub TEXT UNIQUE,
            claimed_affiliation TEXT CHECK (claimed_affiliation IN ('student', 'staff')),
            verified_affiliation TEXT NOT NULL DEFAULT 'pending_verification'
                CHECK (verified_affiliation IN ('student', 'staff', 'pending_verification')),
            matric_number TEXT,
            matric_source TEXT,
            matric_verified INTEGER NOT NULL DEFAULT 0 CHECK (matric_verified IN (0, 1))
        )"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS google_auth_checks (
            token_hash TEXT PRIMARY KEY,
            mode TEXT NOT NULL CHECK (mode IN ('new', 'link', 'existing')),
            user_id TEXT,
            completed_user_id TEXT,
            expires_at INTEGER NOT NULL
        )"""
    )
    check_columns = {row["name"] for row in database.execute("PRAGMA table_info(google_auth_checks)")}
    if "completed_user_id" not in check_columns:
        database.execute("ALTER TABLE google_auth_checks ADD COLUMN completed_user_id TEXT")
    columns = {row["name"] for row in database.execute("PRAGMA table_info(member_identities)")}
    additions = {
        "matric_status": "TEXT NOT NULL DEFAULT 'not_submitted'",
        "matric_key": "TEXT",
        "matric_submitted_at": "TEXT",
        "matric_submitted_email": "TEXT",
        "matric_review_decision": "TEXT",
        "matric_reviewed_by": "TEXT",
        "matric_reviewed_at": "TEXT",
        "matric_rejection_reason": "TEXT",
        "matric_verification_method": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            database.execute(f"ALTER TABLE member_identities ADD COLUMN {name} {definition}")
    # Previous boolean flags have no reviewer audit. Queue them for a fresh review.
    database.execute(
        """UPDATE member_identities SET matric_status = 'pending', matric_verified = 0,
           claimed_affiliation = 'student',
           verified_affiliation = 'pending_verification',
           matric_key = lower(trim(matric_number)),
           matric_submitted_at = COALESCE(matric_submitted_at, ?)
           WHERE matric_verified = 1 AND verified_affiliation = 'student'
             AND matric_number IS NOT NULL AND matric_status = 'not_submitted'""",
        (datetime.now(timezone.utc).isoformat(),),
    )
    database.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_verified_matric
           ON member_identities(matric_key) WHERE matric_status = 'verified'"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS matric_reviews (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, matric_number TEXT NOT NULL,
            decision TEXT NOT NULL CHECK (decision IN ('verified', 'rejected')),
            reviewer_id TEXT NOT NULL, reviewed_at TEXT NOT NULL,
            verification_method TEXT NOT NULL, review_reference TEXT NOT NULL,
            rejection_reason TEXT,
            FOREIGN KEY (user_id) REFERENCES member_identities(user_id)
        )"""
    )
    database.execute(
        """CREATE TABLE IF NOT EXISTS e_merit_eligibility (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, points_reserved INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_approval', created_at TEXT NOT NULL,
            matric_review_id TEXT NOT NULL, required_points INTEGER NOT NULL DEFAULT 50,
            conversion_rate INTEGER NOT NULL DEFAULT 1, reviewer_id TEXT,
            reviewed_at TEXT, decision_reason TEXT, reservation_reference TEXT UNIQUE,
            data_origin TEXT NOT NULL DEFAULT 'production',
            FOREIGN KEY (user_id) REFERENCES member_identities(user_id),
            FOREIGN KEY (matric_review_id) REFERENCES matric_reviews(id)
        )"""
    )
    merit_columns = {row["name"] for row in database.execute("PRAGMA table_info(e_merit_eligibility)")}
    merit_additions = {
        "required_points": "INTEGER NOT NULL DEFAULT 50",
        "conversion_rate": "INTEGER NOT NULL DEFAULT 1",
        "reviewer_id": "TEXT",
        "reviewed_at": "TEXT",
        "decision_reason": "TEXT",
        "reservation_reference": "TEXT",
        "data_origin": "TEXT NOT NULL DEFAULT 'legacy_unknown'",
    }
    for name, definition in merit_additions.items():
        if name not in merit_columns:
            database.execute(f"ALTER TABLE e_merit_eligibility ADD COLUMN {name} {definition}")
    database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_merit_reservation_reference ON e_merit_eligibility(reservation_reference)"
    )
    database.execute(
        "CREATE INDEX IF NOT EXISTS idx_merit_participant_status ON e_merit_eligibility(user_id, status)"
    )
    database.execute(
        "CREATE INDEX IF NOT EXISTS idx_matric_review_participant ON matric_reviews(user_id, reviewed_at)"
    )
    database.executescript(
        """CREATE TRIGGER IF NOT EXISTS trg_merit_reservation_insert
           BEFORE INSERT ON e_merit_eligibility WHEN NEW.data_origin = 'production'
           BEGIN
             SELECT CASE WHEN NEW.points_reserved != 50 OR NEW.required_points != 50
                 OR NEW.conversion_rate != 1 OR NEW.status != 'pending_approval'
                 OR NEW.reservation_reference IS NULL
               THEN RAISE(ABORT, 'invalid E-Merit reservation') END;
             SELECT CASE WHEN NOT EXISTS (
               SELECT 1 FROM member_identities m JOIN matric_reviews v
                 ON v.id = NEW.matric_review_id AND v.user_id = m.user_id
               WHERE m.user_id = NEW.user_id AND m.claimed_affiliation = 'student'
                 AND m.verified_affiliation = 'student' AND m.matric_status = 'verified'
                 AND v.decision = 'verified' AND v.matric_number = m.matric_number)
               THEN RAISE(ABORT, 'verified student review required') END;
             SELECT CASE WHEN (
               SELECT COALESCE(SUM(signed_amount), 0) FROM reward_events
               WHERE user_id = NEW.user_id AND e_merit_classification = 'eligible_student'
                 AND data_origin = 'production'
             ) - (
               SELECT COALESCE(SUM(points_reserved), 0) FROM e_merit_eligibility
               WHERE user_id = NEW.user_id AND status IN ('pending_approval', 'approved', 'converted')
             ) < NEW.points_reserved
               THEN RAISE(ABORT, 'insufficient eligible points') END;
           END;"""
    )


def record_google_check(token: str, mode: str, user_id: str | None = None) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _connect() as database:
        _initialize(database)
        database.execute("DELETE FROM google_auth_checks WHERE expires_at < ?", (int(time.time()),))
        database.execute(
            """INSERT INTO google_auth_checks (token_hash, mode, user_id, expires_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(token_hash) DO UPDATE SET mode = excluded.mode,
                 user_id = excluded.user_id, expires_at = excluded.expires_at
               WHERE google_auth_checks.completed_user_id IS NULL""",
            (token_hash, mode, user_id, int(time.time()) + 300),
        )


def consume_google_check(token: str, user_id: str, *, has_email_identity: bool) -> bool:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _connect() as database:
        _initialize(database)
        database.commit()
        database.execute("BEGIN IMMEDIATE")
        row = database.execute(
            "SELECT mode, user_id, completed_user_id, expires_at FROM google_auth_checks WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if row is None or row["expires_at"] < int(time.time()):
            return False
        if row["completed_user_id"] is not None:
            return row["completed_user_id"] == user_id
        if row["mode"] == "link" and row["user_id"] != user_id:
            return False
        if row["mode"] == "existing" and row["user_id"] != user_id:
            return False
        if row["mode"] == "new" and has_email_identity:
            return False
        database.execute(
            "UPDATE google_auth_checks SET completed_user_id = ? WHERE token_hash = ?",
            (user_id, token_hash),
        )
        return True


def google_owner_id(sub: str) -> str | None:
    """Find a completed local Google association by stable provider subject."""
    with _connect() as database:
        _initialize(database)
        row = database.execute(
            "SELECT user_id FROM member_identities WHERE google_sub = ?", (sub,)
        ).fetchone()
        return row["user_id"] if row else None


def read_identity(user_id: str, email: str, *, email_verified: bool) -> dict[str, object]:
    with _connect() as database:
        _initialize(database)
        database.execute("INSERT OR IGNORE INTO member_identities (user_id) VALUES (?)", (user_id,))
        row = database.execute("SELECT * FROM member_identities WHERE user_id = ?", (user_id,)).fetchone()
        suggestion = suggested_matric(email) if email_verified else None
        if suggestion and row["claimed_affiliation"] != "staff" and not row["matric_verified"] and not row["matric_number"]:
            database.execute(
                "UPDATE member_identities SET matric_number = ?, matric_source = 'verified_email' WHERE user_id = ?",
                (suggestion, user_id),
            )
            row = database.execute("SELECT * FROM member_identities WHERE user_id = ?", (user_id,)).fetchone()
        result = dict(row)
        result["e_merit_identity_eligible"] = (
            row["claimed_affiliation"] == "student"
            and row["verified_affiliation"] == "student"
            and row["matric_status"] == "verified"
            and database.execute(
                "SELECT 1 FROM matric_reviews WHERE user_id = ? AND decision = 'verified' LIMIT 1",
                (user_id,),
            ).fetchone() is not None
        )
        reward_table = database.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reward_events'"
        ).fetchone()
        earned = database.execute(
            """SELECT COALESCE(SUM(signed_amount), 0) FROM reward_events
               WHERE user_id = ? AND e_merit_classification = 'eligible_student'
                 AND data_origin = 'production'""",
            (user_id,),
        ).fetchone()[0] if reward_table and "e_merit_classification" in {
            column["name"] for column in database.execute("PRAGMA table_info(reward_events)")
        } else 0
        reserved = database.execute(
            "SELECT COALESCE(SUM(points_reserved), 0) FROM e_merit_eligibility WHERE user_id = ? AND status IN ('pending_approval', 'approved', 'converted')",
            (user_id,),
        ).fetchone()[0]
        result["e_merit_available_points"] = max(0, earned - reserved)
        return result


def update_identity(user_id: str, email: str, affiliation: str, matric: str | None) -> dict[str, object]:
    """Save a claim or suggested matric without treating it as a submission."""
    with _connect() as database:
        _initialize(database)
        database.execute("INSERT OR IGNORE INTO member_identities (user_id) VALUES (?)", (user_id,))
        row = database.execute("SELECT * FROM member_identities WHERE user_id = ?", (user_id,)).fetchone()
        if affiliation == "staff":
            database.execute(
                """UPDATE member_identities SET claimed_affiliation = 'staff',
                   verified_affiliation = 'pending_verification', matric_number = NULL,
                   matric_key = NULL, matric_source = NULL, matric_verified = 0,
                   matric_status = 'not_submitted', matric_submitted_at = NULL,
                   matric_submitted_email = NULL,
                   matric_review_decision = NULL, matric_reviewed_by = NULL,
                   matric_reviewed_at = NULL, matric_rejection_reason = NULL,
                   matric_verification_method = NULL WHERE user_id = ?""",
                (user_id,),
            )
            database.execute(
                """UPDATE e_merit_eligibility SET status = 'cancelled_affiliation_change'
                   WHERE user_id = ? AND status = 'pending_approval'""",
                (user_id,),
            )
        else:
            if row["matric_status"] in {"pending", "verified"}:
                raise ValueError("Use the matric submission form to change a pending or verified number.")
            source = "verified_email" if matric and matric == suggested_matric(email) else "self_reported"
            database.execute(
                """UPDATE member_identities
                   SET claimed_affiliation = ?, matric_number = ?, matric_source = ?,
                       matric_verified = 0
                   WHERE user_id = ?""",
                (affiliation, matric or None, source if matric else None, user_id),
            )
    return read_identity(user_id, email, email_verified=True)


def submit_matric(user_id: str, email: str, matric: str) -> dict[str, object]:
    """Start or restart review; a changed verified number loses eligibility immediately."""
    matric = matric.strip()
    if not matric:
        raise ValueError("Enter a matric number.")
    with _connect() as database:
        _initialize(database)
        database.commit()
        database.execute("BEGIN IMMEDIATE")
        database.execute("INSERT OR IGNORE INTO member_identities (user_id) VALUES (?)", (user_id,))
        row = database.execute("SELECT * FROM member_identities WHERE user_id = ?", (user_id,)).fetchone()
        if row["matric_status"] not in {"pending", "verified"} or row["matric_number"] != matric:
            if row["matric_status"] == "verified":
                database.execute(
                    """UPDATE e_merit_eligibility SET status = 'cancelled_matric_change'
                       WHERE user_id = ? AND status = 'pending_approval'""",
                    (user_id,),
                )
            source = "verified_email" if matric == suggested_matric(email) else "self_reported"
            database.execute(
                """UPDATE member_identities SET claimed_affiliation = 'student',
                   verified_affiliation = 'pending_verification', matric_number = ?, matric_key = ?,
                   matric_source = ?, matric_verified = 0, matric_status = 'pending',
                   matric_submitted_at = ?, matric_review_decision = NULL,
                   matric_submitted_email = ?,
                   matric_reviewed_by = NULL, matric_reviewed_at = NULL,
                   matric_rejection_reason = NULL, matric_verification_method = NULL
                   WHERE user_id = ?""",
                (matric, matric.casefold(), source, datetime.now(timezone.utc).isoformat(), email.strip().casefold(), user_id),
            )
    return read_identity(user_id, email, email_verified=True)


def activity_affiliation(user_id: str, fallback_claim: str | None = None) -> str:
    """Snapshot the account classification when activity is submitted."""
    with _connect() as database:
        _initialize(database)
        row = database.execute(
            "SELECT claimed_affiliation, verified_affiliation FROM member_identities WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return fallback_claim if fallback_claim in {"student", "staff"} else "unknown"
        claim = row["claimed_affiliation"] or fallback_claim
        if claim == "staff" or row["verified_affiliation"] == "staff":
            return "staff"
        return "student" if claim == "student" else "unknown"


def pending_matric_reviews() -> list[dict[str, object]]:
    with _connect() as database:
        _initialize(database)
        rows = database.execute(
            """SELECT user_id, matric_number, matric_source, matric_submitted_at, matric_submitted_email
               FROM member_identities WHERE matric_status = 'pending'
               ORDER BY matric_submitted_at ASC"""
        ).fetchall()
        return [dict(row) for row in rows]


def review_matric(
    user_id: str, reviewer_id: str, decision: str, method: str,
    reference: str, rejection_reason: str | None,
) -> dict[str, object]:
    if decision not in {"verified", "rejected"}:
        raise ValueError("Invalid review decision.")
    if method not in {"authorized_student_record", "prototype_manual"} or not reference.strip():
        raise ValueError("Record the verification method and what was checked.")
    if decision == "rejected" and not (rejection_reason or "").strip():
        raise ValueError("A rejection reason is required.")
    with _connect() as database:
        _initialize(database)
        database.commit()
        database.execute("BEGIN IMMEDIATE")
        row = database.execute(
            "SELECT * FROM member_identities WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None or row["matric_status"] != "pending":
            raise ValueError("This matric submission is no longer pending.")
        if row["claimed_affiliation"] != "student":
            raise ValueError("Only current student claims can be reviewed.")
        if decision == "verified":
            duplicate = database.execute(
                "SELECT 1 FROM member_identities WHERE matric_key = ? AND matric_status = 'verified' AND user_id != ?",
                (row["matric_key"], user_id),
            ).fetchone()
            if duplicate:
                raise ValueError("This matric number is already assigned to a verified account.")
        now = datetime.now(timezone.utc).isoformat()
        review_id = uuid4().hex
        database.execute(
            """INSERT INTO matric_reviews (id, user_id, matric_number, decision,
               reviewer_id, reviewed_at, verification_method, review_reference, rejection_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (review_id, user_id, row["matric_number"], decision, reviewer_id, now,
             method, reference.strip(), rejection_reason.strip() if rejection_reason else None),
        )
        database.execute(
            """UPDATE member_identities SET matric_status = ?, matric_verified = ?,
               verified_affiliation = ?, matric_review_decision = ?,
               matric_reviewed_by = ?, matric_reviewed_at = ?,
               matric_rejection_reason = ?, matric_verification_method = ?
               WHERE user_id = ?""",
            (decision, int(decision == "verified"),
             "student" if decision == "verified" else "pending_verification",
             decision, reviewer_id, now,
             rejection_reason.strip() if rejection_reason else None, method, user_id),
        )
    return {"user_id": user_id, "decision": decision, "reviewed_at": now}


def create_e_merit_eligibility(user_id: str) -> dict[str, object]:
    """Reserve 50 student-at-submission points for institutional approval."""
    from app.repositories.reports import initialize_database

    with _connect() as database:
        _initialize(database)
        initialize_database(database)
        database.commit()
        database.execute("BEGIN IMMEDIATE")
        identity = database.execute(
            "SELECT claimed_affiliation, verified_affiliation, matric_status FROM member_identities WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not identity or not (
            identity["claimed_affiliation"] == "student"
            and identity["verified_affiliation"] == "student"
            and identity["matric_status"] == "verified"
        ):
            raise ValueError("Verified student matric status is required for E-Merit eligibility.")
        review = database.execute(
            "SELECT id FROM matric_reviews WHERE user_id = ? AND decision = 'verified' ORDER BY reviewed_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if review is None:
            raise ValueError("An admin matric review is required for E-Merit eligibility.")
        # Older reward rows have the safe default 'unknown' and cannot be reclassified.
        earned = database.execute(
            """SELECT COALESCE(SUM(signed_amount), 0) FROM reward_events
               WHERE user_id = ? AND e_merit_classification = 'eligible_student'
                 AND data_origin = 'production'""",
            (user_id,),
        ).fetchone()[0]
        reserved = database.execute(
            "SELECT COALESCE(SUM(points_reserved), 0) FROM e_merit_eligibility WHERE user_id = ? AND status IN ('pending_approval', 'approved', 'converted')",
            (user_id,),
        ).fetchone()[0]
        if earned - reserved < 50:
            raise ValueError("At least 50 available eligible Eco Points are required.")
        record_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        database.execute(
            """INSERT INTO e_merit_eligibility
               (id, user_id, points_reserved, status, created_at, matric_review_id,
                required_points, conversion_rate, reservation_reference, data_origin)
               VALUES (?, ?, 50, 'pending_approval', ?, ?, 50, 1, ?, 'production')""",
            (record_id, user_id, now, review["id"], f"merit:{record_id}"),
        )
        return {"id": record_id, "status": "pending_approval", "points_reserved": 50, "created_at": now}


def save_google_sub(user_id: str, email: str, sub: str) -> dict[str, object]:
    with _connect() as database:
        _initialize(database)
        database.commit()
        database.execute("BEGIN IMMEDIATE")
        database.execute("INSERT OR IGNORE INTO member_identities (user_id) VALUES (?)", (user_id,))
        row = database.execute("SELECT google_sub FROM member_identities WHERE user_id = ?", (user_id,)).fetchone()
        if row["google_sub"] and row["google_sub"] != sub:
            raise ValueError("A different Google account is already connected.")
        owner = database.execute("SELECT user_id FROM member_identities WHERE google_sub = ?", (sub,)).fetchone()
        if owner and owner["user_id"] != user_id:
            raise ValueError("This Google identity is already connected to another account.")
        database.execute("UPDATE member_identities SET google_sub = ? WHERE user_id = ?", (sub, user_id))
    return read_identity(user_id, email, email_verified=True)


def has_google_sub(user_id: str, sub: str) -> bool:
    with _connect() as database:
        _initialize(database)
        row = database.execute(
            "SELECT 1 FROM member_identities WHERE user_id = ? AND google_sub = ?",
            (user_id, sub),
        ).fetchone()
        return row is not None
