"""Versioned forecast persistence. No training occurs in API requests."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.repositories import reports


def _connect(path: Path | None = None):
    target = path or get_settings().hotspot_forecast_database_path
    if target is None:
        return reports._connect()
    target = Path(target).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(db) -> None:
    if get_settings().persistence_backend == "postgres" and get_settings().hotspot_forecast_database_path is None:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS forecast_runs (
        id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, model_name TEXT NOT NULL,
        model_version TEXT NOT NULL, horizon_start TEXT NOT NULL, horizon_end TEXT NOT NULL,
        generated_at TEXT NOT NULL, parameters TEXT NOT NULL, data_provenance TEXT NOT NULL,
        training_metadata TEXT NOT NULL, evaluation_results TEXT NOT NULL,
        status TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS forecast_cells (
        run_id TEXT NOT NULL REFERENCES forecast_runs(id), cell_key TEXT NOT NULL,
        center_latitude REAL NOT NULL, center_longitude REAL NOT NULL,
        predicted_count REAL NOT NULL CHECK(predicted_count >= 0),
        lower_bound REAL, upper_bound REAL, PRIMARY KEY(run_id, cell_key))""")
    db.execute("CREATE INDEX IF NOT EXISTS ix_forecast_latest ON forecast_runs(data_provenance, generated_at)")


def read_reports() -> list[dict]:
    with closing(reports._connect()) as db:
        return [dict(row) for row in db.execute(
            "SELECT id, latitude, longitude, created_at, data_origin FROM reports WHERE data_origin = 'production'"
        ).fetchall()]


def save_batch(batch: dict, *, path: Path | None = None) -> str:
    """Write a complete batch atomically; previous batches remain available."""
    batch_id = str(uuid4())
    db = _connect(path)
    try:
        initialize(db)
        db.execute("BEGIN IMMEDIATE")
        postgres = get_settings().persistence_backend == "postgres" and path is None and get_settings().hotspot_forecast_database_path is None
        for period in batch["periods"]:
            run_id = str(uuid4())
            metadata = json.dumps(batch["training_metadata"], sort_keys=True)
            evaluation = json.dumps(batch["evaluation_results"], sort_keys=True)
            parameters = json.dumps(batch["parameters"], sort_keys=True)
            if postgres:
                db.execute("""INSERT INTO forecast_runs
                    (id,batch_id,model_name,model_version,horizon_start,horizon_end,
                     parameters,data_provenance,training_metadata,evaluation_results,status)
                    VALUES (?::uuid,?::uuid,?,?,?::timestamptz,?::timestamptz,
                            ?::jsonb,?,?::jsonb,?::jsonb,?)""",
                    (run_id,batch_id,batch["model_name"],batch["model_version"],period["start"],period["end"],
                     parameters,batch["provenance"],metadata,evaluation,batch["status"]))
            else:
                db.execute("""INSERT INTO forecast_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id,batch_id,batch["model_name"],batch["model_version"],period["start"],period["end"],
                     batch["generated_at"],parameters,batch["provenance"],metadata,evaluation,batch["status"]))
            for cell in period["cells"]:
                db.execute("""INSERT INTO forecast_cells
                    (run_id,cell_key,center_latitude,center_longitude,predicted_count,lower_bound,upper_bound)
                    VALUES (?,?,?,?,?,NULL,NULL)""",
                    (run_id,cell["cell_key"],cell["center_latitude"],cell["center_longitude"],cell["predicted_count"]))
        db.commit()
        return batch_id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def latest(*, provenance: str = "production", path: Path | None = None) -> dict:
    target = path or get_settings().hotspot_forecast_database_path
    if target is None and get_settings().persistence_backend != "postgres":
        target = reports.DATABASE_PATH
    if target is not None and not Path(target).exists():
        return {"status": "unavailable", "reason": "No trained forecast has been saved.", "periods": []}
    with closing(_connect(path)) as db:
        try:
            row = db.execute("""SELECT batch_id FROM forecast_runs WHERE data_provenance = ?
                ORDER BY generated_at DESC, id DESC LIMIT 1""", (provenance,)).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table: forecast_runs" not in str(exc):
                raise
            row = None
        if row is None:
            return {"status": "unavailable", "reason": "No trained forecast has been saved.", "periods": []}
        runs = [dict(item) for item in db.execute("""SELECT * FROM forecast_runs
            WHERE batch_id = ? ORDER BY horizon_start""", (row["batch_id"],)).fetchall()]
        periods = []
        for run in runs:
            cells = [dict(item) for item in db.execute("""SELECT cell_key,center_latitude,center_longitude,predicted_count
                FROM forecast_cells WHERE run_id = ? ORDER BY cell_key""", (run["id"],)).fetchall()]
            periods.append({"start": str(run["horizon_start"]), "end": str(run["horizon_end"]), "cells": cells})
        first = runs[0]
        def decoded(value): return value if isinstance(value, dict) else json.loads(value)
        return {"status": first["status"], "batch_id": str(first["batch_id"]),
                "model_name": first["model_name"], "model_version": first["model_version"],
                "provenance": first["data_provenance"], "generated_at": str(first["generated_at"]),
                "parameters": decoded(first["parameters"]),
                "training_metadata": decoded(first["training_metadata"]),
                "evaluation_results": decoded(first["evaluation_results"]), "periods": periods}
