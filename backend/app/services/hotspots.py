"""Weekly incident-report-count forecasts on a fixed 0.05 degree grid.

Only submission time and location are used. All lags and rolling statistics
are shifted, so a row never contains its own target or future observations.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from app.services.geo_grid import GRID_DEGREES, grid_cell

MODEL_VERSION = "weekly-grid-005-v1"
MODEL_NAME = "RandomForestRegressor or lag-one baseline"
LAGS = (1, 2, 4, 8)
FEATURES = ["lat_index", "lon_index", "lag_1", "lag_2", "lag_4", "lag_8",
            "rolling_4", "rolling_8", "week_sin", "week_cos"]


def _monday(value: pd.Timestamp) -> pd.Timestamp:
    return value.normalize() - timedelta(days=int(value.weekday()))


def _cell(latitude: float, longitude: float) -> tuple[str, int, int, float, float]:
    key, center_lat, center_lon = grid_cell(latitude, longitude)
    _, lat_index, lon_index = key.split(":")
    return key, int(lat_index), int(lon_index), center_lat, center_lon


def aggregate(reports: list[dict], *, as_of: datetime, provenance: str = "production") -> tuple[pd.DataFrame, dict]:
    """Count reports by UTC Monday and cell; omit the incomplete current week."""
    cutoff = _monday(pd.Timestamp(as_of).tz_convert("UTC") if pd.Timestamp(as_of).tzinfo
                     else pd.Timestamp(as_of).tz_localize("UTC"))
    rows: list[dict] = []
    quality = {"input_records": len(reports), "eligible_records": 0,
               "excluded_origin": 0, "invalid_date": 0, "invalid_location": 0,
               "incomplete_or_future_week": 0}
    for report in reports:
        if report.get("data_origin") != provenance:
            quality["excluded_origin"] += 1
            continue
        try:
            stamp = pd.Timestamp(report["created_at"])
            if pd.isna(stamp): raise ValueError("missing date")
            stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
            week = _monday(stamp)
        except (ValueError, TypeError, OverflowError):
            quality["invalid_date"] += 1
            continue
        try:
            lat, lon = float(report["latitude"]), float(report["longitude"])
            if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("invalid coordinates")
        except (ValueError, TypeError):
            quality["invalid_location"] += 1
            continue
        if week >= cutoff:
            quality["incomplete_or_future_week"] += 1
            continue
        key, li, lo, clat, clon = _cell(lat, lon)
        rows.append({"week": week, "cell_key": key, "lat_index": li, "lon_index": lo,
                     "center_latitude": clat, "center_longitude": clon})
    quality["eligible_records"] = len(rows)
    if not rows:
        return pd.DataFrame(columns=["week", "cell_key", "lat_index", "lon_index",
                                     "center_latitude", "center_longitude", "count"]), quality
    frame = pd.DataFrame(rows)
    grouped = frame.groupby(["week", "cell_key", "lat_index", "lon_index",
                             "center_latitude", "center_longitude"], as_index=False).size()
    return grouped.rename(columns={"size": "count"}), quality


def panel(counts: pd.DataFrame, *, as_of: datetime) -> pd.DataFrame:
    if counts.empty: return counts.copy()
    cutoff = _monday(pd.Timestamp(as_of).tz_convert("UTC") if pd.Timestamp(as_of).tzinfo
                     else pd.Timestamp(as_of).tz_localize("UTC"))
    weeks = pd.date_range(counts.week.min(), cutoff - timedelta(weeks=1), freq="W-MON", tz="UTC")
    cells = counts[["cell_key", "lat_index", "lon_index", "center_latitude", "center_longitude"]].drop_duplicates()
    full = cells.merge(pd.DataFrame({"week": weeks}), how="cross")
    first_seen = counts.groupby("cell_key")["week"].min()
    full = full[full["week"] >= full["cell_key"].map(first_seen)]
    full = full.merge(counts[["cell_key", "week", "count"]], on=["cell_key", "week"], how="left")
    full["count"] = full["count"].fillna(0).astype(int)
    return full.sort_values(["cell_key", "week"]).reset_index(drop=True)


def features(history: pd.DataFrame) -> pd.DataFrame:
    result = history.copy().sort_values(["cell_key", "week"])
    group = result.groupby("cell_key", sort=False)["count"]
    for lag in LAGS: result[f"lag_{lag}"] = group.shift(lag)
    for window in (4, 8):
        result[f"rolling_{window}"] = group.transform(lambda s: s.shift(1).rolling(window).mean())
    week_number = result.week.dt.isocalendar().week.astype(float)
    result["week_sin"] = (2 * math.pi * week_number / 53).map(math.sin)
    result["week_cos"] = (2 * math.pi * week_number / 53).map(math.cos)
    return result.dropna(subset=FEATURES).reset_index(drop=True)


def synthetic_reports(*, as_of: datetime, weeks: int = 72) -> list[dict]:
    """Deterministic demo events, never sourced from real reports."""
    end = _monday(pd.Timestamp(as_of).tz_localize("UTC") if pd.Timestamp(as_of).tzinfo is None
                  else pd.Timestamp(as_of).tz_convert("UTC"))
    result = []
    for age in range(weeks, 0, -1):
        week = end - timedelta(weeks=age)
        for cell_index, (lat, lon) in enumerate(((3.071, 101.512), (3.126, 101.663), (3.211, 101.711))):
            count = max(0, int(2 + cell_index + 1.4 * math.sin(age / 4 + cell_index)
                                + (age % 7 == 0) + (age // 12) % 2))
            for sequence in range(count):
                result.append({"id": f"synthetic-{age}-{cell_index}-{sequence}",
                               "latitude": lat, "longitude": lon,
                               "created_at": (week + timedelta(days=sequence % 6)).isoformat(),
                               "data_origin": "synthetic_demo"})
    return result


def _metrics(actual, prediction) -> dict:
    return {"mae": round(float(mean_absolute_error(actual, prediction)), 4),
            "rmse": round(float(math.sqrt(mean_squared_error(actual, prediction))), 4)}


def _future_features(cell: dict, counts: list[float], week: pd.Timestamp) -> dict:
    number = int(week.isocalendar().week)
    return {"lat_index": cell["lat_index"], "lon_index": cell["lon_index"],
            **{f"lag_{lag}": counts[-lag] for lag in LAGS},
            "rolling_4": sum(counts[-4:]) / 4, "rolling_8": sum(counts[-8:]) / 8,
            "week_sin": math.sin(2 * math.pi * number / 53),
            "week_cos": math.cos(2 * math.pi * number / 53)}


def train(reports: list[dict], *, as_of: datetime, provenance: str,
          horizon_weeks: int = 4) -> tuple[dict, dict | None]:
    if provenance not in {"production", "synthetic_demo"}: raise ValueError("Invalid provenance")
    if not 1 <= horizon_weeks <= 12: raise ValueError("Invalid forecast horizon")
    counts, quality = aggregate(reports, as_of=as_of, provenance=provenance)
    history = panel(counts, as_of=as_of)
    cutoff = _monday(pd.Timestamp(as_of).tz_localize("UTC") if pd.Timestamp(as_of).tzinfo is None
                     else pd.Timestamp(as_of).tz_convert("UTC"))
    generated = datetime.now(timezone.utc).isoformat()
    metadata = {"quality": quality, "grid_degrees": GRID_DEGREES, "week_start": "Monday 00:00 UTC",
                "target": "submitted incident report count", "feature_names": FEATURES,
                "random_state": 42, "as_of_utc": cutoff.isoformat(),
                "pandas_version": pd.__version__, "scikit_learn_version": sklearn.__version__,
                "history_weeks": int(history.week.nunique()) if not history.empty else 0,
                "cells": int(history.cell_key.nunique()) if not history.empty else 0,
                "source": "deterministic synthetic events" if provenance == "synthetic_demo" else "production reports"}
    base = {"model_name": MODEL_NAME, "model_version": MODEL_VERSION, "provenance": provenance,
            "generated_at": generated, "parameters": {"grid_degrees": GRID_DEGREES, "horizon_weeks": horizon_weeks},
            "training_metadata": metadata, "evaluation_results": {}}
    def unavailable(reason: str):
        return ({**base, "status": "insufficient_data", "training_metadata": {**metadata, "reason": reason},
                 "periods": [{"start": cutoff.isoformat(), "end": (cutoff + timedelta(weeks=1)).isoformat(), "cells": []}]}, None)
    if history.empty or metadata["history_weeks"] < 40:
        return unavailable("At least 40 completed weeks are required.")
    if int((history["count"] > 0).groupby(history["week"]).any().sum()) < 20:
        return unavailable("At least 20 reporting weeks are required.")
    rows = features(history)
    if rows.empty: return unavailable("No grid cell has eight prior completed weeks of history.")
    weeks = sorted(rows.week.unique())
    if len(weeks) < 30: return unavailable("Insufficient weeks after lag construction.")
    train_end = int(len(weeks) * 0.6)
    validation_end = int(len(weeks) * 0.8)
    if train_end < 16 or validation_end - train_end < 6 or len(weeks) - validation_end < 6:
        return unavailable("Chronological train, validation, and test windows are too short.")
    train_rows = rows[rows.week.isin(weeks[:train_end])]
    val_rows = rows[rows.week.isin(weeks[train_end:validation_end])]
    test_rows = rows[rows.week.isin(weeks[validation_end:])]
    model = RandomForestRegressor(n_estimators=120, min_samples_leaf=2, random_state=42, n_jobs=1)
    model.fit(train_rows[FEATURES], train_rows["count"])
    baseline_val = _metrics(val_rows["count"], val_rows["lag_1"])
    candidate_val = _metrics(val_rows["count"], model.predict(val_rows[FEATURES]))
    selected = "random_forest" if candidate_val["mae"] < baseline_val["mae"] else "lag_one_baseline"
    # Refit candidate on pre-test rows for an honest untouched test evaluation.
    model.fit(rows[rows.week.isin(weeks[:validation_end])][FEATURES],
              rows[rows.week.isin(weeks[:validation_end])]["count"])
    baseline_test = _metrics(test_rows["count"], test_rows["lag_1"])
    candidate_test = _metrics(test_rows["count"], model.predict(test_rows[FEATURES]))
    evaluation = {"validation": {"baseline": baseline_val, "random_forest": candidate_val},
                  "test": {"baseline": baseline_test, "random_forest": candidate_test},
                  "selected_by_validation_mae": selected,
                  "split_weeks": {"train": train_end, "validation": validation_end - train_end,
                                  "test": len(weeks) - validation_end},
                  "split_ranges": {"train": [str(weeks[0]), str(weeks[train_end - 1])],
                                   "validation": [str(weeks[train_end]), str(weeks[validation_end - 1])],
                                   "test": [str(weeks[validation_end]), str(weeks[-1])]}}
    metadata["training_window"] = [str(weeks[0]), str(weeks[-1])]
    metadata["last_completed_week"] = str(history.week.max())
    metadata["forecastable_cells"] = int(rows.cell_key.nunique())
    metadata["excluded_short_cell_history"] = int(history.cell_key.nunique() - rows.cell_key.nunique())
    if selected == "random_forest": model.fit(rows[FEATURES], rows["count"])
    artifact = {"model_version": MODEL_VERSION, "selected": selected,
                "feature_names": FEATURES, "estimator": model if selected == "random_forest" else None,
                "training_metadata": metadata, "evaluation_results": evaluation}
    forecastable = set(rows.cell_key)
    series = {key: group["count"].astype(float).tolist()
              for key, group in history.groupby("cell_key") if key in forecastable}
    cells = history[history.cell_key.isin(forecastable)][
        ["cell_key", "lat_index", "lon_index", "center_latitude", "center_longitude"]
    ].drop_duplicates().to_dict("records")
    periods = []
    for step in range(horizon_weeks):
        week = cutoff + timedelta(weeks=step)
        predictions = []
        for cell in cells:
            prior = series[cell["cell_key"]]
            future = _future_features(cell, prior, week)
            prediction = (float(model.predict(pd.DataFrame([future])[FEATURES])[0])
                          if selected == "random_forest" else prior[-1])
            prediction = round(max(0.0, prediction), 3)
            prior.append(prediction)
            predictions.append({"cell_key": cell["cell_key"],
                                "center_latitude": cell["center_latitude"],
                                "center_longitude": cell["center_longitude"],
                                "predicted_count": prediction})
        periods.append({"start": week.isoformat(), "end": (week + timedelta(weeks=1)).isoformat(),
                        "cells": predictions})
    return {**base, "status": "available", "evaluation_results": evaluation, "periods": periods}, artifact


def save_artifact(path: Path, artifact: dict) -> str:
    """Only trusted local artifacts should be loaded; checksum detects corruption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(artifact, temporary)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    temporary.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="ascii")
    return digest


def load_artifact(path: Path) -> dict:
    expected = path.with_suffix(path.suffix + ".sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("Forecast artifact checksum mismatch")
    artifact = joblib.load(path)  # trusted local files only; never accept a request path
    if artifact.get("model_version") != MODEL_VERSION or artifact.get("feature_names") != FEATURES:
        raise ValueError("Incompatible forecast artifact")
    return artifact
