"""Privacy-limited administrative analytics over submitted report cohorts."""
from __future__ import annotations

import csv
import io
import re
import statistics
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.repositories import reports
from app.services.geo_grid import grid_cell


@dataclass(frozen=True)
class Filters:
    start: date | None = None
    end: date | None = None
    category: str | None = None
    status: str | None = None
    area: str | None = None
    provenance: str = "production"

    def __post_init__(self):
        if self.start and self.end and self.start > self.end:
            raise ValueError("Start date must be on or before end date.")
        if self.provenance not in {"production", "legacy_unknown", "demo"}:
            raise ValueError("Invalid provenance.")
        if self.area:
            match = re.fullmatch(r"g005:(-?\d+):(-?\d+)", self.area)
            if not match or not (-1800 <= int(match[1]) <= 1799 and -3600 <= int(match[2]) <= 3599):
                raise ValueError("Invalid grid area.")


def _time(value) -> datetime | None:
    if value is None: return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _area(row: dict) -> tuple[str, float, float] | None:
    try:
        lat, lon = float(row["latitude"]), float(row["longitude"])
        return grid_cell(lat, lon)
    except (ValueError, TypeError, KeyError):
        return None


def _rows(db, table: str, columns: str) -> list[dict]:
    try:
        return [dict(row) for row in db.execute(f"SELECT {columns} FROM {table}").fetchall()]
    except Exception as exc:
        # Existing SQLite installations may not yet have Phase 2 assignment tables.
        if table in {"report_assignments", "cleanup_proofs"} and "no such table" in str(exc):
            return []
        raise


def snapshot(filters: Filters) -> dict:
    with closing(reports._connect()) as db:
        raw = _rows(db, "reports", "id,reference,category,status,latitude,longitude,created_at,data_origin")
        events = _rows(db, "report_status_events", "report_id,previous_status,new_status,created_at")
        assignments = _rows(db, "report_assignments", "id,report_id,assignee_id,team_name,assigned_at,ended_at")
        proofs = _rows(db, "cleanup_proofs", "assignment_id")
    selected = []
    invalid_dates = 0
    for row in raw:
        if row["data_origin"] != filters.provenance: continue
        submitted = _time(row["created_at"])
        if submitted is None:
            invalid_dates += 1
            continue
        if filters.start and submitted.date() < filters.start: continue
        if filters.end and submitted.date() > filters.end: continue
        if filters.category and row["category"] != filters.category: continue
        if filters.status and row["status"] != filters.status: continue
        area = _area(row)
        if filters.area and (area is None or area[0] != filters.area): continue
        selected.append({**row, "submitted": submitted, "area": area})
    ids = {row["id"] for row in selected}
    resolved_events = defaultdict(list)
    for event in events:
        if (event["report_id"] in ids and event["previous_status"] == "pending_verification"
                and event["new_status"] == "resolved"):
            stamp = _time(event["created_at"])
            if stamp: resolved_events[event["report_id"]].append(stamp)
    by_status = Counter(row["status"] for row in selected)
    by_category = Counter(row["category"] for row in selected)
    reported_days = Counter(row["submitted"].date().isoformat() for row in selected)
    resolved_days = Counter()
    durations = []
    verified = {}
    for row in selected:
        if row["status"] != "resolved" or not resolved_events[row["id"]]: continue
        event_time = min(resolved_events[row["id"]])
        if event_time < row["submitted"]: continue
        verified[row["id"]] = event_time
        durations.append((event_time - row["submitted"]).total_seconds() / 3600)
        resolved_days[event_time.date().isoformat()] += 1
    days = sorted(set(reported_days) | set(resolved_days))
    assignment_rows = [a for a in assignments if a["report_id"] in ids]
    proof_ids = {p["assignment_id"] for p in proofs}
    by_staff = defaultdict(lambda: {"assigned": 0, "active": 0, "verified_completions": 0})
    for a in assignment_rows:
        staff = by_staff[a["assignee_id"]]
        staff["assigned"] += 1
        if a["ended_at"] is None: staff["active"] += 1
    completions = 0
    for report_id, verified_at in verified.items():
        matching = [a for a in assignment_rows if a["report_id"] == report_id
                    and (_time(a["assigned_at"]) or verified_at) <= verified_at]
        if matching:
            chosen = max(matching, key=lambda a: _time(a["assigned_at"]) or datetime.min.replace(tzinfo=timezone.utc))
            if chosen["id"] in proof_ids:
                by_staff[chosen["assignee_id"]]["verified_completions"] += 1
                completions += 1
    heat = Counter(row["area"] for row in selected if row["area"] is not None)
    heatmap = [{"cell_key": key[0], "center_latitude": key[1], "center_longitude": key[2], "count": count}
               for key, count in sorted(heat.items())]
    total = len(selected)
    metrics = {"total_submitted": total, "by_status": dict(sorted(by_status.items())),
               "by_category": dict(sorted(by_category.items())),
               "resolved_current": by_status["resolved"],
               "resolution_rate_percent": round(100 * by_status["resolved"] / total, 2) if total else None,
               "verified_resolution_count": len(durations),
               "average_resolution_hours": round(statistics.mean(durations), 2) if durations else None,
               "median_resolution_hours": round(statistics.median(durations), 2) if durations else None,
               "staff": {"task_assignments": len(assignment_rows),
                         "active_assignments": sum(a["ended_at"] is None for a in assignment_rows),
                         "verified_completions_with_proof": completions,
                         "by_staff": [{"staff_id": key, **value} for key, value in sorted(by_staff.items())]},
               "missing_coordinates": sum(row["area"] is None for row in selected),
               "resolved_without_verified_timestamp": by_status["resolved"] - len(durations),
               "invalid_source_dates": invalid_dates}
    safe_reports = [{"reference": row["reference"], "category": row["category"],
                     "status": row["status"], "submitted_at": row["submitted"].isoformat(),
                     "area": row["area"][0] if row["area"] else "",
                     "verified_resolved_at": verified[row["id"]].isoformat() if row["id"] in verified else ""}
                    for row in selected]
    return {"filters": {"start": filters.start.isoformat() if filters.start else None,
                        "end": filters.end.isoformat() if filters.end else None,
                        "category": filters.category, "status": filters.status,
                        "area": filters.area, "provenance": filters.provenance},
            "generated_at": datetime.now(timezone.utc).isoformat(), "metrics": metrics,
            "trends": [{"date": day, "reported": reported_days[day], "resolved": resolved_days[day]} for day in days],
            "observed_heatmap": heatmap, "reports": safe_reports}


EXPORT_COLUMNS = ("reference", "category", "status", "submitted_at", "area", "verified_resolved_at")


def csv_export(data: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(EXPORT_COLUMNS)
    for row in data["reports"]:
        writer.writerow([_safe_csv(str(row[column])) for column in EXPORT_COLUMNS])
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def _safe_csv(value: str) -> str:
    # Spreadsheets may ignore leading whitespace before interpreting a formula.
    dangerous = value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))
    return "'" + value if dangerous else value
