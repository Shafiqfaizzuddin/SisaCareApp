"""Opaque, revocable browser sessions with idle and absolute expiry."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from typing import Any

from app.core.config import get_settings


def _connect() -> sqlite3.Connection:
    path = get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, timeout=10)
    database.row_factory = sqlite3.Row
    return database


def _initialize(database: sqlite3.Connection) -> None:
    database.execute("""CREATE TABLE IF NOT EXISTS browser_sessions (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        user_json TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL
    )""")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create(user: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    with _connect() as database:
        _initialize(database)
        database.execute("INSERT INTO browser_sessions VALUES (?, ?, ?, ?, ?)",
                         (_hash(token), user["id"], json.dumps(user), now, now))
    return token


def read(token: str) -> dict[str, Any] | None:
    if len(token) > 256:
        return None
    settings = get_settings()
    now = int(time.time())
    with _connect() as database:
        _initialize(database)
        database.execute("BEGIN IMMEDIATE")
        row = database.execute("SELECT * FROM browser_sessions WHERE token_hash = ?", (_hash(token),)).fetchone()
        if row is None:
            return None
        if now - row["created_at"] >= settings.session_absolute_seconds or now - row["last_seen_at"] >= settings.session_idle_seconds:
            database.execute("DELETE FROM browser_sessions WHERE token_hash = ?", (_hash(token),))
            return None
        database.execute("UPDATE browser_sessions SET last_seen_at = ? WHERE token_hash = ?", (now, _hash(token)))
        return json.loads(row["user_json"])


def revoke(token: str) -> None:
    with _connect() as database:
        _initialize(database)
        database.execute("DELETE FROM browser_sessions WHERE token_hash = ?", (_hash(token),))
