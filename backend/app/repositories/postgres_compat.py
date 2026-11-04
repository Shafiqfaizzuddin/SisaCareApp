"""Small SQLite-call-site adapter for the versioned Supabase PostgreSQL schema.

The compatibility columns keep the established API stable while the normalized
tables are populated alongside them. This module does not create schema at runtime.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.core.config import get_settings


class Record(dict):
    """A row with the named and positional access used by sqlite3.Row callers."""

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _record_factory(cursor: Any):
    names = [column.name for column in cursor.description]

    def make(values: Iterable[Any]) -> Record:
        return Record(zip(names, values))

    return make


def translate_sql(statement: str) -> str:
    """Translate the limited SQLite DML used by the existing repositories."""
    sql = statement.strip()
    if re.fullmatch(r"BEGIN IMMEDIATE", sql, re.IGNORECASE):
        return ""
    sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.IGNORECASE)
    if re.search(r"\bINSERT\s+INTO\b", sql, re.IGNORECASE) and "OR IGNORE" in statement.upper():
        sql = sql.rstrip("; ") + " ON CONFLICT DO NOTHING"
    sql = re.sub(r"\bCOLLATE\s+NOCASE\b", 'COLLATE "C"', sql, flags=re.IGNORECASE)
    sql = re.sub(r"\browid\b", "id", sql, flags=re.IGNORECASE)
    return sql.replace("?", "%s")


class PostgresConnection:
    def __init__(self) -> None:
        import psycopg

        self._connection = psycopg.connect(
            get_settings().postgres_database_url.get_secret_value(),
            row_factory=_record_factory,
            options="-c search_path=sisacare,public",
        )

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()):
        import psycopg

        sql = statement.strip()
        pragma = re.fullmatch(r"PRAGMA\s+table_info\((\w+)\)", sql, re.IGNORECASE)
        if pragma:
            return self._connection.execute(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema = 'sisacare' AND table_name = %s ORDER BY ordinal_position",
                (pragma.group(1),),
            )
        if sql.upper() == "PRAGMA FOREIGN_KEYS = ON" or sql.upper() == "BEGIN IMMEDIATE":
            return self._connection.execute("SELECT 1 WHERE false")
        if "sqlite_master" in sql:
            sql = sql.replace("sqlite_master", "information_schema.tables")
            sql = sql.replace("type = 'table'", "table_schema = 'sisacare'")
            sql = sql.replace("name =", "table_name =")
        translated = translate_sql(sql)
        return self._connection.execute(translated, parameters)

    def executemany(self, statement: str, parameters: Iterable[tuple[Any, ...]]):
        with self._connection.cursor() as cursor:
            cursor.executemany(translate_sql(statement), parameters)
            return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type, _exc, _traceback) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def connect() -> PostgresConnection:
    return PostgresConnection()
