# Phase 2 collection workflow

## Apply and preserve data

1. Back up the existing SQLite file and the Supabase database. Keep the original SQLite file; this phase does not delete or rewrite it.
2. Apply `supabase/migrations/20261104000100_csp650_phase1.sql` first if it has not already been applied. Then apply `supabase/migrations/20261104000200_csp650_phase2.sql` with the Supabase CLI (`supabase db push`) against the intended project. Review the linked project before running the command.
3. Verify the `sisacare.role_grants`, `sisacare.report_assignments`, `sisacare.cleanup_proofs`, and `sisacare.report_status_events` tables and the partial unique index `ux_active_report_assignment`. Confirm the `sisacare-private` bucket remains private.
4. Set backend `PERSISTENCE_BACKEND=postgres`, `POSTGRES_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and **server only** `SUPABASE_SERVICE_ROLE_KEY`. Keep the React app limited to the publishable key. Existing upload settings (`MAX_UPLOAD_SIZE`, `MAX_IMAGE_PIXELS`) also apply to cleanup proof.
5. Use an existing trusted administrator account whose Supabase **app metadata** has `role=admin`. The administrator signs in at `/admin/login`, opens `/admin/staff`, and grants `staff` or `driver` to an existing Supabase Auth user UUID. The server verifies that UUID with Supabase Auth before writing a grant. Staff and drivers sign in at `/staff/login`.

After applying the migration, run these read-only checks in the Supabase SQL editor and compare report counts to the pre-migration backup:

```sql
select count(*) from sisacare.reports;
select report_id, count(*) from sisacare.report_assignments
 where ended_at is null group by report_id having count(*) > 1;
select p.id from sisacare.cleanup_proofs p
 left join sisacare.report_assignments a on a.id = p.assignment_id
 where a.id is null;
select count(*) from sisacare.reports where status = 'resolved' and resolution_seconds is not null;
```

The duplicate and orphan queries should return no rows. The final count includes only resolutions verified through the new workflow; historical resolved rows remain without invented values. To roll back an application deployment, restore the previous backend/frontend release and keep the newly added tables and columns until their data has been backed up. Do not drop the original SQLite file.

## API and state machine

| Actor | Route | Purpose |
| --- | --- | --- |
| Admin | `GET /api/collection/admin/staff` | List role grants |
| Admin | `POST /api/collection/admin/staff/grants` | Grant `staff` or `driver` to an existing Auth user |
| Admin | `DELETE /api/collection/admin/staff/grants/{user_id}/{role}` | Revoke a grant |
| Admin | `POST /api/collection/admin/tasks/{report_id}/assign` | Assign or reassign a verified or active report |
| Staff | `GET /api/collection/tasks` | List active assignments for the signed-in user |
| Staff | `GET /api/collection/tasks/{report_id}` | View an assigned task |
| Staff | `POST /api/collection/tasks/{report_id}/start` | `assigned` → `in_progress` |
| Staff | `POST /api/collection/tasks/{report_id}/submit` | Multipart `note` and `image`; `in_progress` → `pending_verification` |
| Admin | `POST /api/collection/admin/tasks/{report_id}/verify` | `pending_verification` → `resolved` |
| Admin | `POST /api/collection/admin/tasks/{report_id}/rework` | `pending_verification` → `in_progress`, requires reason |
| Admin | `POST /api/collection/admin/tasks/{report_id}/reject` | `pending_verification` → `rejected`, requires reason |

The legacy `POST /api/reports/{report_id}/assignment` contract now requires `assignee_id` and accepts `reason`; it uses the same transition service. The legacy admin resolution route returns HTTP 410 because direct resolution would bypass staff proof and verification. Citizen and admin report reads retain their existing response fields and include the new statuses. The citizen report detail page displays the status history.

Every transition appends actor, previous/new status, timestamp, and reason. A report row is locked during each mutation; the database also enforces a single active assignment. Reassignments require a reason and end the previous assignment without deleting it. Historical `in_progress` reports can be adopted by an administrator with a reason, producing an `in_progress` → `assigned` history event. Existing resolved reports are retained; they are not given fabricated cleanup proof or resolution time. New resolution time is the number of seconds from original report submission to administrator verification.

An administrator can request rework while a task is pending verification; this returns it to the assigned staff member and requires a fresh submission with proof. Rejection is a terminal review decision and closes the assignment. Staff grants are checked on each authenticated request, so revocation immediately blocks further staff actions; the administrator can reassign an affected task with a recorded reason.

Cleanup photos use the private `sisacare-private` bucket in PostgreSQL mode. The API checks image extension, MIME, upload size, decoded image content, and task ownership. Storage object reads pass through authenticated FastAPI endpoints. A failed database transition removes a newly uploaded object when possible. Local SQLite mode stores proof under `REPORT_ASSETS_DIR/cleanup`; it is for development and tests.

## Verify

Run `backend/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_csp650_phase2.py` from `backend`, then `npm run build` from `frontend`. In a staging Supabase project, sign in as citizen, admin, and two staff users. Confirm a citizen and an unassigned staff user receive 403/404 for protected actions, that a second assignment needs a reason, that submission without proof fails, and that rework retains both proof records and all history. Verify the citizen sees `resolved` only after administrator verification and the `resolution_seconds` value is populated. A live Supabase migration and end-to-end storage test require project credentials and are not represented by local tests.
