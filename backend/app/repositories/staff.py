"""Explicit staff grants; only trusted administrator routes may mutate them."""
from __future__ import annotations

from uuid import UUID

from app.core.config import get_settings
from app.repositories import reports


def initialize(database) -> None:
    if get_settings().persistence_backend == "postgres":
        return
    reports.initialize_database(database)
    database.execute("""CREATE TABLE IF NOT EXISTS role_grants (
        user_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('staff','driver')),
        granted_by TEXT NOT NULL, granted_at TEXT NOT NULL, revoked_at TEXT,
        email TEXT, display_name TEXT, invited_at TEXT,
        PRIMARY KEY(user_id, role))""")
    existing = {row["name"] for row in database.execute("PRAGMA table_info(role_grants)")}
    for column in ("email", "display_name", "invited_at"):
        if column not in existing:
            database.execute(f"ALTER TABLE role_grants ADD COLUMN {column} TEXT")
    database.execute("""CREATE TABLE IF NOT EXISTS report_assignments (
        id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id),
        team_name TEXT NOT NULL, assignee_id TEXT NOT NULL, assigned_by TEXT NOT NULL,
        assigned_at TEXT NOT NULL, ended_at TEXT)""")
    database.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_active_assignment ON report_assignments(report_id) WHERE ended_at IS NULL")
    database.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_assignment_proof_parent ON report_assignments(report_id, id, assignee_id)")
    database.execute("""CREATE TABLE IF NOT EXISTS cleanup_proofs (
        id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES reports(id),
        assignee_id TEXT NOT NULL, assignment_id TEXT NOT NULL REFERENCES report_assignments(id),
        object_key TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL, sha256 TEXT NOT NULL,
        byte_size INTEGER NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(report_id, assignment_id, assignee_id)
          REFERENCES report_assignments(report_id, id, assignee_id) ON DELETE RESTRICT)""")


def active_role(user_id: str) -> str | None:
    with reports._connect() as database:
        initialize(database)
        row = database.execute("""SELECT role FROM role_grants WHERE user_id = ?
            AND revoked_at IS NULL AND role IN ('staff','driver') ORDER BY role LIMIT 1""", (user_id,)).fetchone()
        return row["role"] if row else None


def list_staff() -> list[dict]:
    with reports._connect() as database:
        initialize(database)
        return [dict(row) for row in database.execute(
            "SELECT user_id, role, granted_by, granted_at, revoked_at, email, display_name, invited_at FROM role_grants ORDER BY granted_at DESC"
        ).fetchall()]


def active_grant(user_id: str) -> dict | None:
    with reports._connect() as database:
        initialize(database)
        row = database.execute(
            """SELECT user_id, role, email, display_name, invited_at FROM role_grants
               WHERE user_id = ? AND revoked_at IS NULL AND role IN ('staff','driver')
               ORDER BY granted_at DESC LIMIT 1""", (user_id,),
        ).fetchone()
        return dict(row) if row else None


def set_grant(user_id: str, role: str, actor_id: str, *, revoke: bool = False,
              email: str | None = None, display_name: str | None = None,
              invited: bool = False) -> None:
    UUID(user_id); UUID(actor_id)
    if role not in {"staff", "driver"} or user_id == actor_id:
        raise ValueError("A distinct Auth user and staff or driver role are required.")
    with reports._connect() as database:
        initialize(database)
        if revoke:
            database.execute("UPDATE role_grants SET revoked_at = ? WHERE user_id = ? AND role = ?",
                             (reports._utc_now(), user_id, role))
        else:
            now = reports._utc_now()
            database.execute("UPDATE role_grants SET revoked_at = ? WHERE user_id = ? AND role IN ('staff','driver') AND role <> ? AND revoked_at IS NULL",
                             (now, user_id, role))
            database.execute("""INSERT INTO role_grants(user_id, role, granted_by, granted_at, revoked_at, email, display_name, invited_at)
                VALUES (?, ?, ?, ?, NULL, ?, ?, ?) ON CONFLICT(user_id, role) DO UPDATE SET
                granted_by = excluded.granted_by, granted_at = excluded.granted_at, revoked_at = NULL,
                email = COALESCE(excluded.email, role_grants.email),
                display_name = COALESCE(excluded.display_name, role_grants.display_name),
                invited_at = COALESCE(excluded.invited_at, role_grants.invited_at)""",
                (user_id, role, actor_id, now, email, display_name, now if invited else None))
