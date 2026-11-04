from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import copy
import sqlite3

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from app.core.auth import require_admin_user, require_authenticated_user
from app.main import app
from app.repositories import forecasts
from app.services.hotspots import (FEATURES, aggregate, features, load_artifact, panel,
                                   save_artifact, synthetic_reports, train)

AS_OF = datetime(2026, 11, 2, tzinfo=timezone.utc)


def test_grid_aggregation_and_provenance() -> None:
    records = [
        {"latitude": 3.071, "longitude": 101.512, "created_at": "2026-10-20T10:00:00+00:00", "data_origin": "production"},
        {"latitude": 3.072, "longitude": 101.513, "created_at": "2026-10-25T23:00:00+00:00", "data_origin": "production"},
        {"latitude": 3.071, "longitude": 101.512, "created_at": "2026-10-20", "data_origin": "synthetic_demo"},
        {"latitude": None, "longitude": 101.512, "created_at": "2026-10-20", "data_origin": "production"},
        {"latitude": 3.071, "longitude": 101.512, "created_at": "2026-11-02", "data_origin": "production"},
    ]
    frame, quality = aggregate(records, as_of=AS_OF)
    assert frame["count"].tolist() == [2]
    assert quality == {"input_records": 5, "eligible_records": 2, "excluded_origin": 1,
                       "invalid_date": 0, "invalid_location": 1, "incomplete_or_future_week": 1}


def test_lags_and_rolling_features_use_only_prior_weeks() -> None:
    records = synthetic_reports(as_of=AS_OF, weeks=44)
    counts, _ = aggregate(records, as_of=AS_OF, provenance="synthetic_demo")
    history = panel(counts, as_of=AS_OF)
    before = features(history)
    last_week = history.week.max()
    altered = history.copy()
    altered.loc[altered.week == last_week, "count"] = 100000
    after = features(altered)
    current = before.week == last_week
    pd.testing.assert_frame_equal(before.loc[current, FEATURES].reset_index(drop=True),
                                  after.loc[current, FEATURES].reset_index(drop=True))
    assert (before.loc[current, "count"] != after.loc[current, "count"]).all()


def test_new_cell_does_not_exist_before_first_report() -> None:
    records = synthetic_reports(as_of=AS_OF, weeks=44)
    late = {"latitude": 4.001, "longitude": 102.001,
            "created_at": "2026-10-20T12:00:00+00:00", "data_origin": "synthetic_demo"}
    counts, _ = aggregate(records + [late], as_of=AS_OF, provenance="synthetic_demo")
    history = panel(counts, as_of=AS_OF)
    late_rows = history[history.cell_key == "g005:80:2040"]
    assert len(late_rows) == 2
    assert late_rows["count"].tolist() == [1, 0]
    assert "g005:80:2040" not in set(features(history).cell_key)


def test_insufficient_history_is_explicit() -> None:
    batch, artifact = train(synthetic_reports(as_of=AS_OF, weeks=12), as_of=AS_OF,
                            provenance="synthetic_demo")
    assert batch["status"] == "insufficient_data"
    assert batch["periods"][0]["cells"] == []
    assert artifact is None


def test_train_save_load_and_forecast_isolation(tmp_path: Path) -> None:
    batch, artifact = train(synthetic_reports(as_of=AS_OF), as_of=AS_OF,
                            provenance="synthetic_demo")
    assert batch["status"] == "available"
    assert len(batch["periods"]) == 4
    assert len(batch["periods"][0]["cells"]) == 3
    assert all(cell["predicted_count"] >= 0 for period in batch["periods"] for cell in period["cells"])
    assert batch["evaluation_results"]["split_weeks"]["test"] >= 6
    ranges = batch["evaluation_results"]["split_ranges"]
    assert ranges["train"][1] < ranges["validation"][0] < ranges["test"][0]
    path = tmp_path / "model.joblib"
    save_artifact(path, artifact)
    assert load_artifact(path)["model_version"] == batch["model_version"]
    path.with_suffix(".joblib.sha256").write_text("bad", encoding="ascii")
    with pytest.raises(ValueError, match="checksum"): load_artifact(path)
    db = tmp_path / "demo.db"
    forecasts.save_batch(batch, path=db)
    saved = forecasts.latest(provenance="synthetic_demo", path=db)
    assert saved["status"] == "available" and len(saved["periods"]) == 4
    assert forecasts.latest(provenance="production", path=db)["status"] == "unavailable"
    invalid = copy.deepcopy(batch)
    invalid["periods"][1]["cells"][0]["predicted_count"] = -1
    with pytest.raises(sqlite3.IntegrityError): forecasts.save_batch(invalid, path=db)
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT COUNT(DISTINCT batch_id) FROM forecast_runs").fetchone()[0] == 1


def test_admin_endpoint_authorization_and_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "missing.db"
    from app.core.config import Settings
    monkeypatch.setattr(forecasts, "get_settings", lambda: Settings(_env_file=None, hotspot_forecast_database_path=db))
    client = TestClient(app)
    with client:
        response = client.get("/api/admin/hotspots/forecasts")
        assert response.status_code == 401
        app.dependency_overrides[require_authenticated_user] = lambda: {"id": "citizen", "role": "user"}
        try:
            assert client.get("/api/admin/hotspots/forecasts").status_code == 403
        finally:
            app.dependency_overrides.clear()
        app.dependency_overrides[require_admin_user] = lambda: {"id": "admin", "role": "admin"}
        try:
            result = client.get("/api/admin/hotspots/forecasts")
            assert result.status_code == 200 and result.json()["status"] == "unavailable"
            assert not db.exists()
            batch, _ = train(synthetic_reports(as_of=AS_OF, weeks=12), as_of=AS_OF,
                             provenance="synthetic_demo")
            forecasts.save_batch(batch, path=db)
            saved = client.get("/api/admin/hotspots/forecasts?provenance=synthetic_demo")
            assert saved.status_code == 200
            assert saved.json()["status"] == "insufficient_data"
            assert saved.json()["provenance"] == "synthetic_demo"
            assert client.get("/api/admin/hotspots/forecasts?provenance=invalid").status_code == 422
        finally:
            app.dependency_overrides.clear()
