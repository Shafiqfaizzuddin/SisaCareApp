# Predictive report hotspots (backend)

## Target and evidence

The target is the number of **submitted incident reports** in each area during an upcoming UTC week. It is not waste mass, physical volume, cleanup demand, or an incident probability. All statuses are included because later review decisions would leak future knowledge. Only records marked `data_origin=production` with valid coordinates and timestamps in completed weeks enter production training. Legacy records with unknown provenance, missing coordinates, and the current incomplete week are excluded and counted in training metadata.

Areas are fixed 0.05° latitude/longitude grid cells aligned to integer multiples of 0.05°. Keys are `g005:<floor(latitude/0.05)>:<floor(longitude/0.05)>`. Their centers are approximate display points; the area is angular and varies in physical width with latitude. The model forecasts only cells observed for at least nine completed weeks, so eight prior-week features are available. Do not interpret an absent cell as a predicted zero or use this grid as a municipal boundary.

The local SQLite database inspected during development contained 11 reports over about four weeks, including seven marked production. At the November 4 cutoff, only four production records had completed-week dates and valid coordinates; three were in the incomplete current week. It cannot support a meaningful holdout. Production training with that history returns `insufficient_data` rather than a numeric forecast. Recheck current data quality with the training command; these figures are an inspection snapshot, not a live metric.

## Reproduce training and evaluation

From `backend`, install `pip install -e '.[analytics]'` in the backend virtual environment. Apply `supabase/migrations/20261104000300_hotspot_forecasts.sql` after the Phase 1 and Phase 2 migrations when using Supabase PostgreSQL. Configure `PERSISTENCE_BACKEND=postgres` and server-only `POSTGRES_DATABASE_URL` for production, or retain SQLite for local development. Never put database credentials in the React environment.

```powershell
cd backend
python scripts/train_hotspots.py --as-of 2026-11-02T00:00:00+00:00
python scripts/train_hotspots.py --synthetic-demo --as-of 2026-11-02T00:00:00+00:00 --output-db hotspot-artifacts/demo.db --artifact hotspot-artifacts/demo.joblib
```

Omit `--as-of` for a scheduled current run. A forecast refresh is another invocation of the same command. Keep training in a scheduled job or operator terminal; report submission and forecast GET requests never train a model. The command prints source counts, exclusion counts, status, and evaluation. Each run saves a new batch; prior batches remain for audit. It never deletes or rewrites report records.

For the synthetic demo, set `HOTSPOT_FORECAST_DATABASE_PATH` to the absolute path of `hotspot-artifacts/demo.db` in the backend environment and request `GET /api/admin/hotspots/forecasts?provenance=synthetic_demo`. This separate SQLite database contains forecast output only, never synthetic report rows. The synthetic generator is deterministic, has three fixed cells and 72 completed weeks, and is clearly labeled `synthetic_demo` in every stored batch. The training command refuses to write synthetic output to the configured report SQLite file. Remove the override to serve production forecasts from the configured PostgreSQL or SQLite application database. The default endpoint provenance is `production`.

## Method and evaluation

The panel zero fills completed weeks between each cell's first observed week and the cutoff; newly observed cells never appear in earlier training rows. Features are cell indices, prior counts at one, two, four, and eight weeks, rolling means of the prior four and eight weeks, and sine/cosine of the calendar week. There are no holiday indicators. Every count feature uses only weeks strictly before its target week. At least 40 completed weeks and 20 weeks with reports are required. After eight weeks of lag construction, unique weeks are split chronologically: first 60% train, next 20% validation, last 20% test. At least 16/6/6 weeks are required in these windows.

The baseline repeats the prior week's count. The candidate is `RandomForestRegressor` with 120 trees, minimum leaf size 2, random state 42 and one worker. Validation MAE selects the model; validation and test MAE/RMSE for both are stored. The candidate is refit on train plus validation for test evaluation, then on all completed history for forecasting if selected. These holdout scores are **one week ahead** scores with the previous observed week known. The four-week published forecast uses recursive predictions for later lags, so its multiweek uncertainty can be greater than the reported holdout errors. Predicted counts are nonnegative expected report counts, stored as decimals; they are not fabricated observed counts. No prediction intervals are asserted.

`hotspot-artifacts/*.joblib` is a trusted local artifact with a SHA-256 sidecar. `load_artifact` checks the checksum and model version. Joblib deserialization is unsafe for untrusted files: never accept an artifact path or artifact bytes from an API request. The admin API reads database snapshots and does not load artifacts.

## API and access

`GET /api/admin/hotspots/forecasts?provenance=production` requires the existing authenticated administrator dependency. It returns `status`, batch/model version, provenance, training and evaluation metadata, and periods with grid keys, centers, and predicted counts. Before the first run it returns `status=unavailable`; a failed history gate stores `status=insufficient_data` and no cells. Staff and citizens receive 403; unauthenticated clients receive 401. Invalid provenance receives 422. No training or mutation endpoint exists.

The Supabase migration enables RLS and permits `SELECT` on forecast tables only to authenticated users passing `sisacare.is_admin()`. The `sisacare` schema is not exposed through the default Supabase Data API. Server-side FastAPI authorization remains mandatory because the backend PostgreSQL connection uses server credentials. Run migrations using the established Supabase migration process, then verify the policy as citizen and administrator. No live Supabase connection was available for this local implementation, so PostgreSQL migration application and live RLS checks remain deployment steps.

## Verification and operational checks

Run `python -m pytest tests/test_hotspots.py` from `backend`. Before publishing a production dashboard, review `training_metadata.quality`, the train/validation/test week counts, and both model scores. If the model is not better than the lag-one baseline on validation MAE, the saved forecasts use the baseline. If history is insufficient, accumulate more weeks; do not relabel synthetic output as production.
