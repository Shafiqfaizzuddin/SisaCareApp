"""Repeatable, conservative SQLite -> Supabase PostgreSQL/Storage cutover.

Dry-run is the default. Apply only while the SQLite application is stopped and
after making an independent backup. The source database is opened read-only.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


TABLE_ORDER = (
    "analysis_drafts", "reports", "waste_detections", "report_status_events",
    "report_email_outbox", "recycling_points", "recycling_actions",
    "reward_events", "public_participants", "member_identities",
    "google_auth_checks", "matric_reviews", "e_merit_eligibility",
    "education_articles", "browser_sessions",
)
PRIMARY_KEYS = {name: ("event_key" if name == "report_email_outbox" else
                       "user_id" if name in {"public_participants", "member_identities"} else
                       "token_hash" if name in {"google_auth_checks", "browser_sessions"} else "id")
                for name in TABLE_ORDER}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
REPORT_URL = re.compile(r"^/api/reports/files/([0-9a-f]{32})/(original|annotated|after)\.(jpg|jpeg|png|webp)$")
RECYCLING_URL = re.compile(r"^/api/recycling/files/([0-9a-f]{32})/(original|proof)\.(jpg|jpeg|png|webp)$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint(path: Path) -> str:
    """Include WAL bytes, which may contain committed rows absent from the main file."""
    digest = hashlib.sha256()
    for source in (path, Path(str(path) + "-wal")):
        digest.update(source.name.encode("utf-8"))
        digest.update(sha256_file(source).encode("ascii") if source.exists() else b"absent")
    return digest.hexdigest()


def source_connection(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    database = sqlite3.connect(uri, uri=True)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    return database


def inspect_source(database: sqlite3.Connection) -> tuple[dict[str, int], list[str]]:
    existing = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    counts = {name: database.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
              for name in TABLE_ORDER if name in existing}
    errors = []
    for violation in database.execute("PRAGMA foreign_key_check"):
        errors.append(f"SQLite foreign key: {tuple(violation)}")
    missing = [name for name in TABLE_ORDER if name not in existing]
    if missing:
        errors.append("Snapshot upgrade did not create tables: " + ", ".join(missing))
    return counts, errors


def asset_manifest(database: sqlite3.Connection, root: Path) -> tuple[list[tuple[str, str, Path]], list[str]]:
    """Return (bucket, key, local path), including unreferenced retained files."""
    root = root.resolve()
    assets: dict[tuple[str, str], Path] = {}
    errors: list[str] = []
    if root.exists():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                errors.append(f"Asset escapes root: {path}")
                continue
            relative = path.relative_to(root)
            if relative.parts[0] == "education":
                bucket, key = "sisacare-education", f"articles/{relative.name}"
            elif relative.parts[0] == "recycling":
                bucket, key = "sisacare-private", relative.as_posix()
            else:
                bucket, key = "sisacare-private", f"reports/{relative.as_posix()}"
            if (bucket, key) in assets and assets[(bucket, key)] != resolved:
                errors.append(f"Storage key collision: {bucket}/{key}")
            assets[(bucket, key)] = resolved
    for table, columns, pattern, prefix in (
        ("reports", ("original_image", "annotated_image", "after_photo"), REPORT_URL, "reports"),
        ("recycling_actions", ("original_photo", "proof_photo"), RECYCLING_URL, "recycling"),
    ):
        for row in database.execute(f"SELECT * FROM {table}"):
            for column in columns:
                value = row[column]
                if not value:
                    continue
                match = pattern.fullmatch(value)
                if not match or match.group(1) != row["id"]:
                    errors.append(f"Unexpected {table}.{column} URL for {row['id']}")
                    continue
                key = f"{prefix}/{row['id']}/{Path(value).name}"
                if ("sisacare-private", key) not in assets:
                    errors.append(f"Missing referenced image: {table}.{column} for {row['id']}")
    for row in database.execute("SELECT id, image_filename FROM education_articles WHERE image_filename IS NOT NULL"):
        filename = row["image_filename"]
        if Path(filename).name != filename or ("sisacare-education", f"articles/{filename}") not in assets:
            errors.append(f"Missing Learn image for article {row['id']}")
    return [(bucket, key, path) for (bucket, key), path in sorted(assets.items())], errors


def import_rows(source: sqlite3.Connection, target) -> dict[str, int]:
    """Insert unchanged legacy rows; fail if a target key has different data."""
    imported: dict[str, int] = {}
    for table in TABLE_ORDER:
        rows = source.execute(f"SELECT * FROM {table}").fetchall()
        columns = [col["name"] for col in source.execute(f"PRAGMA table_info({table})")]
        key = PRIMARY_KEYS[table]
        for row in rows:
            values = tuple(row[column] for column in columns)
            target.execute(
                f"INSERT INTO sisacare.{table} ({', '.join(columns)}) "
                f"VALUES ({', '.join(['%s'] * len(columns))}) ON CONFLICT ({key}) DO NOTHING",
                values,
            )
            current = target.execute(
                f"SELECT {', '.join(columns)} FROM sisacare.{table} WHERE {key} = %s",
                (row[key],),
            ).fetchone()
            if current is None or any(current[index] != values[index] for index in range(len(columns))):
                raise ValueError(f"Conflicting existing row in {table}: {row[key]}")
        imported[table] = len(rows)
    return imported


def import_normalized(source: sqlite3.Connection, target, assets: list[tuple[str, str, Path]]) -> dict[str, int]:
    asset_lookup = {(bucket, key): path for bucket, key, path in assets}
    counts = {"report_images": 0, "recycling_images": 0, "article_images": 0,
              "ai_results": 0, "report_assignments": 0, "notifications": 0}
    media = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

    def add_image(table: str, owner_field: str, owner_id: str, kind: str, bucket: str, key: str) -> None:
        path = asset_lookup[(bucket, key)]
        target.execute(
            f"INSERT INTO sisacare.{table} ({owner_field}, image_kind, bucket_id, object_key, content_type, sha256, byte_size) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (object_key) DO NOTHING",
            (owner_id, kind, bucket, key, media[path.suffix.lower()], sha256_file(path), path.stat().st_size),
        )
        counts[table] += 1

    for row in source.execute("SELECT * FROM reports"):
        for kind, column in (("original", "original_image"), ("annotated", "annotated_image"), ("after", "after_photo")):
            if row[column]:
                add_image("report_images", "report_id", row["id"], kind, "sisacare-private",
                          f"reports/{row['id']}/{Path(row[column]).name}")
        raw = row["ai_analysis_json"]
        reviewed = row["confirmed_ai_result_json"]
        target.execute(
            """INSERT INTO sisacare.ai_results (report_id, analysis_id, raw_result, reviewed_result)
               VALUES (%s, %s, %s::jsonb, %s::jsonb) ON CONFLICT (report_id) DO NOTHING""",
            (row["id"], row["analysis_id"], raw, reviewed),
        )
        counts["ai_results"] += 1
        if row["assigned_team"]:
            target.execute(
                """INSERT INTO sisacare.report_assignments (id, report_id, team_name)
                   VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                (uuid5(NAMESPACE_URL, "sisacare:assignment:" + row["id"]), row["id"], row["assigned_team"]),
            )
            counts["report_assignments"] += 1
    for row in source.execute("SELECT * FROM recycling_actions"):
        for kind, column in (("original", "original_photo"), ("proof", "proof_photo")):
            if row[column]:
                add_image("recycling_images", "action_id", row["id"], kind, "sisacare-private",
                          f"recycling/{row['id']}/{Path(row[column]).name}")
    for row in source.execute("SELECT * FROM education_articles WHERE image_filename IS NOT NULL"):
        key = f"articles/{row['image_filename']}"
        path = asset_lookup[("sisacare-education", key)]
        target.execute(
            """INSERT INTO sisacare.article_images
               (article_id, object_key, content_type, sha256, byte_size)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT (object_key) DO NOTHING""",
            (row["id"], key, media[path.suffix.lower()], sha256_file(path), path.stat().st_size),
        )
        counts["article_images"] += 1
    for row in source.execute("SELECT event_key, report_id, event_type, created_at, sent_at, attempts, last_error FROM report_email_outbox"):
        delivery_status = ("sent" if row["sent_at"] else "failed" if row["attempts"] >= 5
                           else "retrying" if row["attempts"] else "queued")
        target.execute(
            """INSERT INTO sisacare.notifications
               (report_id, recipient_id, event_type, channel, outbox_event_key,
                created_at, delivery_status, attempts, last_error, delivered_at)
               SELECT r.id, u.id, %s, 'email', %s, %s::timestamptz, %s, %s, %s, %s::timestamptz FROM sisacare.reports r
               LEFT JOIN auth.users u ON u.id::text = r.user_id WHERE r.id = %s
               ON CONFLICT (outbox_event_key) DO NOTHING""",
            (row["event_type"], row["event_key"], row["created_at"], delivery_status,
             row["attempts"], row["last_error"], row["sent_at"], row["report_id"]),
        )
        counts["notifications"] += 1
    target.execute("INSERT INTO sisacare.profiles (user_id) SELECT id FROM auth.users ON CONFLICT DO NOTHING")
    return counts


def upload_assets(assets: list[tuple[str, str, Path]]) -> list[tuple[str, str]]:
    from app.services.supabase_storage import get_file, put_file
    import httpx

    created: list[tuple[str, str]] = []
    try:
        for bucket, key, path in assets:
            try:
                put_file(key, path, bucket=bucket)
                created.append((bucket, key))
            except httpx.HTTPStatusError as exc:
                try:
                    error_code = str(exc.response.json().get("code", ""))
                except (ValueError, AttributeError):
                    error_code = ""
                if exc.response.status_code not in {400, 409} or (
                    exc.response.status_code == 400 and error_code not in {"ResourceAlreadyExists", "Duplicate"}
                ):
                    raise
                remote_digest = hashlib.sha256(get_file(key, bucket=bucket)).hexdigest()
                if remote_digest != sha256_file(path):
                    raise ValueError(f"Different object already exists: {bucket}/{key}") from exc
    except Exception:
        clean_created(created)
        raise
    return created


def clean_created(created: list[tuple[str, str]]) -> None:
    from app.services.supabase_storage import delete_file

    for bucket, key in reversed(created):
        try:
            delete_file(key, bucket=bucket)
        except Exception as exc:
            print(f"Manual cleanup may be needed for {bucket}/{key}: {type(exc).__name__}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Import into configured Supabase PostgreSQL/Storage")
    args = parser.parse_args()
    if not args.sqlite.is_file():
        parser.error("SQLite source file does not exist")
    if os.environ.get("PERSISTENCE_BACKEND", "sqlite") != "sqlite":
        parser.error("Run the migration with PERSISTENCE_BACKEND=sqlite; switch the app only after verification")
    before_hash = source_fingerprint(args.sqlite)
    with tempfile.TemporaryDirectory(prefix="sisacare-migration-") as temp_dir:
      snapshot_path = Path(temp_dir) / "source.db"
      with closing(source_connection(args.sqlite)) as original, closing(sqlite3.connect(snapshot_path)) as snapshot:
          original.backup(snapshot)
      # Upgrade only the isolated snapshot using the app's existing additive
      # SQLite migrations. The original database remains open read-only.
      from app.repositories import browser_sessions, identities, reports

      with closing(sqlite3.connect(snapshot_path)) as snapshot:
          snapshot.row_factory = sqlite3.Row
          old_columns = {row[1] for row in snapshot.execute("PRAGMA table_info(reports)")}
          generated_detection_reports: list[str] = []
          if "detection_json" in old_columns:
              generated_detection_reports = [row[0] for row in snapshot.execute(
                  """SELECT r.id FROM reports r WHERE r.detection_json IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM waste_detections d WHERE d.report_id = r.id)""")]
          reports.initialize_database(snapshot)
          for report_id in generated_detection_reports:
              for index, row in enumerate(snapshot.execute(
                  "SELECT rowid FROM waste_detections WHERE report_id = ? ORDER BY rowid", (report_id,)
              ).fetchall()):
                  snapshot.execute(
                      "UPDATE waste_detections SET id = ? WHERE rowid = ?",
                      (uuid5(NAMESPACE_URL, f"sisacare:legacy-detection:{report_id}:{index}").hex, row[0]),
                  )
          identities._initialize(snapshot)
          snapshot.execute("""CREATE TABLE IF NOT EXISTS education_articles (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL,
              body TEXT NOT NULL, image_filename TEXT, image_alt TEXT NOT NULL DEFAULT '',
              published INTEGER NOT NULL DEFAULT 1, sort_order INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
          browser_sessions._initialize(snapshot)
          snapshot.commit()
      with closing(source_connection(snapshot_path)) as source:
          counts, errors = inspect_source(source)
          if not errors:
              assets, asset_errors = asset_manifest(source, args.assets)
              errors.extend(asset_errors)
          else:
              assets = []
          result = {"source_sha256": before_hash, "row_counts": counts,
                    "asset_counts": {bucket: sum(item[0] == bucket for item in assets)
                                     for bucket in {item[0] for item in assets}},
                    "errors": errors, "mode": "apply" if args.apply else "dry-run"}
          print(json.dumps(result, indent=2, sort_keys=True))
          if errors:
              return 2
          if not args.apply:
              return 0
          database_url = os.environ.get("POSTGRES_DATABASE_URL", "")
          if not database_url or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or not os.environ.get("SUPABASE_URL"):
              parser.error("Apply requires POSTGRES_DATABASE_URL, SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the server environment")
          import psycopg

          created = upload_assets(assets)
          try:
              with psycopg.connect(database_url, options="-c search_path=sisacare,public") as target:
                  target.execute(
                      """INSERT INTO sisacare.migration_runs (source_sha256)
                         VALUES (%s) ON CONFLICT (source_sha256) DO NOTHING""",
                      (before_hash,),
                  )
                  imported = import_rows(source, target)
                  normalized = import_normalized(source, target, assets)
                  for table, expected in imported.items():
                      actual = target.execute(f"SELECT COUNT(*) FROM sisacare.{table}").fetchone()[0]
                      if actual < expected:
                          raise ValueError(f"Target {table} has {actual} rows; expected at least {expected}")
                  target.execute(
                      """UPDATE sisacare.migration_runs SET completed_at = now(),
                         row_counts = %s::jsonb, asset_counts = %s::jsonb WHERE source_sha256 = %s""",
                      (json.dumps(imported), json.dumps(normalized), before_hash),
                  )
                  if source_fingerprint(args.sqlite) != before_hash:
                      raise ValueError("SQLite source changed during import; stop writes and retry")
              print(json.dumps({"status": "committed", "row_counts": imported,
                                "normalized_counts": normalized}, indent=2))
          except Exception:
              clean_created(created)
              raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
