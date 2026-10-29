"""Admin-managed public learning articles. No historical report tables are changed."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from app.repositories import reports


INITIAL_ARTICLES = (
    ("Household waste", "Bulky furniture, appliances, food waste, and mixed domestic items.", "Use scheduled bulky-waste collection or an approved community facility."),
    ("Recyclables", "Clean paper, cardboard, glass, metal, and accepted plastics.", "Separate clean materials and check what the collection point accepts."),
    ("Construction debris", "Concrete, timber, tiles, soil, plasterboard, and renovation offcuts.", "Arrange collection through an appropriate construction-waste contractor."),
    ("Hazardous or unknown waste", "Chemicals, batteries, paint, oils, and unidentified containers.", "Do not touch or move suspicious materials. Report them for assessment."),
    ("Stay safe around waste", "Keep people away from leaking containers, sharp materials, smoke, or chemical smells.", "Do not open or move unknown containers. Contact emergency services if there is an immediate threat."),
    ("Take a useful report photo", "Show the waste and the surrounding access area from a safe distance.", "Include a visible landmark where possible, without approaching hazards."),
)


def _initialize(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS education_articles (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        body TEXT NOT NULL,
        image_filename TEXT,
        image_alt TEXT NOT NULL DEFAULT '',
        published INTEGER NOT NULL DEFAULT 1 CHECK (published IN (0, 1)),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    # Seed once. Once administrators have edited or unpublished the content,
    # it is never replaced by application startup.
    if not db.execute("SELECT 1 FROM education_articles LIMIT 1").fetchone():
        now = reports._utc_now()
        db.executemany(
            """INSERT INTO education_articles
               (id, title, summary, body, sort_order, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(uuid4().hex, title, summary, body, index, now, now)
             for index, (title, summary, body) in enumerate(INITIAL_ARTICLES)],
        )


def _serialize(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"], "title": row["title"], "summary": row["summary"],
        "body": row["body"], "image_url":
        f"/api/education/articles/{row['id']}/image" if row["image_filename"] else None,
        "image_alt": row["image_alt"], "published": bool(row["published"]),
        "sort_order": row["sort_order"], "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_articles(*, published_only: bool) -> list[dict[str, object]]:
    with reports._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)
        db.commit()
        rows = db.execute(
            "SELECT * FROM education_articles WHERE (? = 0 OR published = 1) ORDER BY sort_order, created_at, id",
            (int(published_only),),
        ).fetchall()
        return [_serialize(row) for row in rows]


def get_article(article_id: str) -> sqlite3.Row | None:
    with reports._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)
        db.commit()
        return db.execute("SELECT * FROM education_articles WHERE id = ?", (article_id,)).fetchone()


def save_article(data: dict[str, object], article_id: str | None = None) -> dict[str, object] | None:
    with reports._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)
        now = reports._utc_now()
        if article_id is None:
            article_id = uuid4().hex
            db.execute("""INSERT INTO education_articles
                (id, title, summary, body, image_alt, published, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (article_id, data["title"], data["summary"], data["body"],
                 data["image_alt"], int(data["published"]), data["sort_order"], now, now))
        else:
            cursor = db.execute("""UPDATE education_articles SET title = ?, summary = ?, body = ?,
                image_alt = ?, published = ?, sort_order = ?, updated_at = ? WHERE id = ?""",
                (data["title"], data["summary"], data["body"], data["image_alt"],
                 int(data["published"]), data["sort_order"], now, article_id))
            if cursor.rowcount == 0:
                db.rollback()
                return None
        row = db.execute("SELECT * FROM education_articles WHERE id = ?", (article_id,)).fetchone()
        db.commit()
        return _serialize(row)


def set_image(article_id: str, filename: str | None, alt: str = "") -> str | None:
    with reports._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _initialize(db)
        row = db.execute("SELECT image_filename FROM education_articles WHERE id = ?", (article_id,)).fetchone()
        if row is None:
            db.rollback()
            raise LookupError("Article not found.")
        db.execute("UPDATE education_articles SET image_filename = ?, image_alt = ?, updated_at = ? WHERE id = ?",
                   (filename, alt, reports._utc_now(), article_id))
        db.commit()
        return row["image_filename"]
