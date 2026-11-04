# CSP650 Phase 1: Supabase PostgreSQL and Storage cutover

This phase retains the current citizen/admin screens, report statuses, local Florence-2/Ollama services, and FastAPI routes. It moves application records from SQLite to Supabase PostgreSQL and permanent report, recycling proof, and Learn article images to Supabase Storage. The original SQLite database and local image tree are never deleted by the migration script.

## Schema and relationship decisions

The versioned Supabase CLI migration is `supabase/migrations/20261104000100_csp650_phase1.sql`. It creates a private `sisacare` schema. Compatibility tables preserve every current SQLite column and text primary key so existing API contracts and historical IDs remain stable. Foreign keys preserve report → analysis draft, detection/status/outbox → report, recycling action → point/draft, reward → report/action, and matric/E-Merit relationships. Original timestamps, statuses, reward amounts, and Learn content are imported unchanged.

New normalized tables are `profiles` (FK to `auth.users.id` UUID), `role_grants`, `report_images`, `recycling_images`, `article_images`, `ai_results`, `report_assignments`, `notifications`, `forecast_runs`, `forecast_cells`, and `migration_runs`. Existing `reports.user_id` remains text because historical guest/legacy rows can lack a matching Auth user; active authenticated reports still contain the existing Supabase Auth UUID string, and RLS compares it to `auth.uid()::text`. Forecasting tables are schema only; Phase 4 owns the model and UI. The Phase 2 staff workflow is likewise not introduced here.

The SQLite source may predate several additive tables. The script takes a SQLite backup into a temporary file and runs the existing SQLite schema upgrade on that copy only. The source is opened read-only. The upgraded copy supplies the import, while the original file remains unchanged. Learn articles absent from an old source are not invented during import; the existing application seeds them on first use after cutover.

The two buckets are private: `sisacare-private` for report and recycling images, and `sisacare-education` for Learn images. All client Storage operations are denied in Phase 1. FastAPI uses its server-only service credential to upload/download, after checking admin or action ownership through existing API dependencies. A public Learn route serves only a published article's current image; a private bucket prevents direct access to unpublished images. Report image routes retain their admin-only contract.

## Prerequisites

1. Install the backend dependencies from `backend/pyproject.toml`, including `psycopg[binary]`. Install the Supabase CLI. Apply the migration to a disposable/staging Supabase project first using the [Supabase migration workflow](https://supabase.com/docs/guides/deployment/database-migrations).
2. Stop writes to the SQLite app. Make independent copies of `backend/storage/sisacare.db`, any `-wal` file, and `backend/storage/reports`. Keep those backups outside the cutover directory. Do not turn on PostgreSQL mode before the import succeeds.
3. Confirm the Supabase project has the same Auth users as the current app. Review existing `app_metadata.role=admin` grants with an authorized operator. No email-domain or user-supplied role becomes admin. The new role-grant table is reserved for controlled grants; the current FastAPI admin check still uses trusted Supabase `app_metadata`.
4. Run `supabase migration list --remote`, then `supabase db push --remote` for the linked staging project. The migration creates the schema, RLS policies, and private buckets. Avoid manually creating duplicate tables in the Dashboard.

## Server-only configuration

Set these in `backend/.env` or deployment secrets. Never use a `VITE_` prefix or put database/secret credentials in `frontend/.env.*`.

| Variable | Purpose |
| --- | --- |
| `PERSISTENCE_BACKEND` | `sqlite` during import; switch to `postgres` after verification. |
| `POSTGRES_DATABASE_URL` | Supabase direct or session-pooler PostgreSQL URL. Include TLS configuration such as `sslmode=require`. Keep server-only. |
| `SUPABASE_URL` | Same Supabase project already used by Auth. |
| `SUPABASE_PUBLISHABLE_KEY` | Existing Auth verification configuration. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only Storage transfer credential. Never put it in React. |
| `REPORT_ASSETS_DIR` / `DATABASE_PATH` | Existing local source and rollback paths; retained after cutover. |

No frontend environment change is needed. The browser still calls FastAPI and Supabase Auth through its existing contracts. The backend PostgreSQL connection uses `search_path=sisacare,public`; the custom schema is not exposed to the Supabase Data API by default. RLS and SELECT policies protect owner/admin reads if the schema is exposed later. Anonymous users and authenticated clients have no write grants. The server database credential can bypass RLS, so FastAPI's role/ownership checks remain mandatory. See the [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security) and [Storage access](https://supabase.com/docs/guides/storage/security/access-control) guides.

## Dry run, import, and verification

From the repository root, with the application stopped:

```powershell
backend/.venv/Scripts/python.exe scripts/migrate_sqlite_to_supabase.py --sqlite backend/storage/sisacare.db --assets backend/storage/reports
```

Review `row_counts`, `asset_counts`, and `errors`. Missing referenced photos, invalid paths, and SQLite FK violations block apply. The dry run makes no PostgreSQL or Storage request. On this repository's current local SQLite source, the observed dry run found one report, six detections, and two referenced images with no errors; this is not a statement about any deployed database.

With `PERSISTENCE_BACKEND=sqlite` still set and the three server-only connection variables present in the process environment, run:

```powershell
backend/.venv/Scripts/python.exe scripts/migrate_sqlite_to_supabase.py --sqlite backend/storage/sisacare.db --assets backend/storage/reports --apply
```

The script uploads immutable object keys, compares an existing object by SHA-256 on rerun, imports unchanged IDs in one PostgreSQL transaction, rejects conflicting existing rows, checks counts and source stability, and records a run in `sisacare.migration_runs`. A failed database transaction rolls back; the script attempts to remove only objects it created in that attempt and prints any object needing manual cleanup. It does not delete the source SQLite file or original assets. A completed rerun is safe when source and target values match; conflicting target rows stop the run.

After apply, inspect `sisacare.migration_runs`, compare every imported table count and sample IDs/content to the source, and confirm each referenced image has a matching `report_images`, `recycling_images`, or `article_images` row and can be fetched through its authorized API. Verify `auth.users` UUIDs match current reports; review any historical orphan user IDs separately instead of manufacturing Auth users. Test citizen A cannot read citizen B's report, a non-admin cannot open `/api/reports/files/...`, and unpublished Learn images are unavailable via public routes. Confirm a new citizen report, AI draft, admin verification/assignment/resolution, notification outbox, recycling action, and Learn edit persist after a backend restart. Test a production-like Tunnel deployment with HTTPS and a configured SMTP sender if notifications are in scope.

Only then set `PERSISTENCE_BACKEND=postgres` and restart FastAPI. Do not run SQLite and PostgreSQL writers against the same user traffic during cutover. The local AI temporary upload/preview files still live on the laptop while an analysis is in progress; permanent images live in Storage.

## Rollback and limits

If validation fails before the switch, keep `PERSISTENCE_BACKEND=sqlite`; the original database is still authoritative. If validation fails after the switch, stop FastAPI, preserve a PostgreSQL backup of new writes, and restore the independent SQLite backup plus assets before switching back to `sqlite`. Reconcile reports created during the PostgreSQL interval before reopening writes; a simple flag reversal would lose those new records. Do not run `supabase db reset` against a live project. Do not remove or overwrite the original SQLite data automatically.

This code change was not applied to a live Supabase project in this workspace. PostgreSQL migration execution, RLS behavior against real Auth JWTs, Storage transfer, and post-cutover API behavior require the staging checks above. The repository's local SQLite dry run and automated tests cover code paths but cannot prove hosted configuration or network delivery.
