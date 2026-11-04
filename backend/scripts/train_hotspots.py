"""Offline hotspot training: python scripts/train_hotspots.py --help"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import BACKEND_ROOT, get_settings  # noqa: E402
from app.repositories import forecasts  # noqa: E402
from app.services.hotspots import save_artifact, synthetic_reports, train  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Train/evaluate weekly incident report-count forecasts")
    parser.add_argument("--synthetic-demo", action="store_true", help="Use deterministic demo events only")
    parser.add_argument("--output-db", type=Path, help="Separate SQLite forecast DB (required for demo)")
    parser.add_argument("--artifact", type=Path, help="Trusted local model artifact path")
    parser.add_argument("--as-of", help="UTC timestamp; default: current time")
    parser.add_argument("--horizon-weeks", type=int, default=4)
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else datetime.now(timezone.utc)
    if as_of.tzinfo is None: parser.error("--as-of must include a time zone")
    if args.synthetic_demo:
        if args.output_db is None: parser.error("--synthetic-demo requires --output-db")
        if args.output_db.resolve() == get_settings().database_path.resolve():
            parser.error("Demo output must not be the report database")
        source = synthetic_reports(as_of=as_of)
        provenance = "synthetic_demo"
    else:
        if args.output_db is not None:
            parser.error("Production forecasts use the configured application database")
        source = forecasts.read_reports()
        provenance = "production"
    batch, artifact = train(source, as_of=as_of, provenance=provenance, horizon_weeks=args.horizon_weeks)
    artifact_path = args.artifact or BACKEND_ROOT / "hotspot-artifacts" / f"{provenance}.joblib"
    if artifact is not None:
        batch["training_metadata"]["artifact_sha256"] = save_artifact(artifact_path, artifact)
        batch["training_metadata"]["artifact_path"] = str(artifact_path.resolve())
    batch_id = forecasts.save_batch(batch, path=args.output_db)
    print(json.dumps({"batch_id": batch_id, "status": batch["status"],
                      "provenance": provenance, "quality": batch["training_metadata"]["quality"],
                      "evaluation": batch["evaluation_results"],
                      "periods": len(batch["periods"]),
                      "reason": batch["training_metadata"].get("reason")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
