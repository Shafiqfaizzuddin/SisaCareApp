# CSP650 phased implementation plan

This plan follows the static findings in [CSP650_IMPLEMENTATION_AUDIT.md](CSP650_IMPLEMENTATION_AUDIT.md). Preserve existing account IDs, reports, AI audit data, images, and historical statuses. Use a staging Supabase project and a copy of the local database before changing live data. The laptop can continue to host FastAPI, Florence-2, and Ollama through the existing Tunnel; Supabase becomes the durable application store required by CSP650.

## Phase 0 — freeze contracts and baseline

1. Confirm the course rubric's exact meaning of “classification percentages,” “predictive,” “severity/volume,” and “cleanup proof.” Record a field-level acceptance contract and sample screenshots/exports.
2. Inventory local SQLite row counts, foreign-key relationships, image references, report statuses, draft/AI versions, and notification outbox records. Back up database and assets before migration. Keep a manifest and checksums.
3. Define report state transitions explicitly: `reported` (map existing `submitted`), optional admin `verified` review, `assigned` (team and assignee recorded), `in_progress` (staff acceptance/start), `resolved` (staff proof submitted and admin acceptance, or clearly documented admin-only demo policy), plus `rejected`. Preserve legacy values as historical facts, not silently rewritten.
4. Decide whether the authority is a real operations partner or a demo team; do not imply real municipal assignment. Define evidence retention, location precision, photo consent, and export access.

**Gate:** approved state diagram, role/action matrix, data dictionary, migration manifest, and privacy decisions. No production migration yet.

## Phase 1 — Supabase application persistence and roles

1. Add versioned SQL migrations under `supabase/migrations/` for profiles/role grants, reports, detections and reviewed items, status events, assignments, cleanup evidence, notification outbox, and immutable migration IDs. Use UUID user references to `auth.users`, created/updated timestamps, foreign keys, checks, and indexes for owner, status, time, and geospatial queries. Keep model outputs and human corrections distinguishable.
2. Create private Storage buckets for incident originals, analysis previews, and cleanup proof. Store object keys and content metadata in tables. Server-side upload and signed-read endpoints can preserve current frontend behavior while limiting file size/type and preventing arbitrary bucket reads.
3. Implement RLS for owner-visible reports, assigned-staff-only work, and trusted admin access. Prefer a controlled server-side role table or trusted `app_metadata` grants; never derive privileges from email domain or user-editable metadata. Keep service-role credentials only on the backend. Audit grant/revocation and session refresh.
4. Replace SQLite as the write authority via repository interfaces. Migrate in dependency order, import each asset once, preserve source IDs and original timestamps, validate counts and hashes, and perform read reconciliation. Avoid unbounded dual writes; use a brief cutover with rollback to the backed-up local state. Retain SQLite as archival/rollback data until sign-off.

**Gate:** staging migrations/reconciliation pass; negative RLS tests prove citizen cross-access and staff cross-team access fail; private photo access and grant revocation are verified; no report/image loss. Confirm Supabase Database and Storage in the hosted project, not merely Auth.

## Phase 2 — Staff/Driver workflow and cleanup proof

1. Add trusted `staff`/`driver` permissions in backend auth/types and separate staff routes/UI. Scope assignments to a user/team and show only assigned jobs. Keep admin review/override paths explicit.
2. Implement server-validated transitions with expected-state checks, actor/time audit events, idempotency keys where needed, and concurrency control. Record `assigned` independently from `in_progress`; keep `verified` and `rejected` as review outcomes.
3. Require cleanup proof for resolution: after-photo, time, location or reason for unavailable GPS, staff identity, and cleanup note. Validate type/size/image decode, private storage, and linkage to the report. Define admin acceptance/rejection or reopen behavior. Historical resolved records should be labeled “legacy proof unavailable” where appropriate, not fabricated.
4. Update citizen tracking, admin queue, and staff task pages to reflect the same state machine. Make accessible status labels and allow admins to inspect before/after evidence.

**Gate:** API authorization/transition tests, duplicate-action/concurrent-update tests, owner visibility tests, and a staging end-to-end citizen → admin → staff → admin/citizen demonstration.

## Phase 3 — AI measures with honest provenance

1. Keep existing Florence detections and rule categories, but specify a measurable class-percentage method. Florence currently provides no confidence value; do not display a model score as a probability. Choose an evaluated classifier or a calibrated separate classification stage and save model/version, raw scores, calibration method, and “unavailable/needs confirmation” states.
2. Define severity and volume as separate estimates with units/bins, input features, uncertainty, and human override. For a demo, a conservative visual size bin with explicit “cannot infer scale from image” may be more defensible than kilograms. Use user-supplied quantity only as user data. Avoid turning detection count into physical volume.
3. Build a labeled evaluation set including mixed waste, occlusion, low light, and out-of-scope photos. Assess class calibration, severity agreement, and volume error. Set thresholds and fallback behavior before showing percentages in the citizen/admin UI.

**Gate:** documented dataset, metrics and limitations; UI distinguishes model estimate from verified classification; no unsupported percentage, severity, or volume claim.

## Phase 4 — hotspots, metrics, notifications, exports

1. Start with historical density by grid/area and time window. Exclude rejected/duplicate or imprecise reports as policy dictates; protect citizen location privacy through aggregation and minimum counts. Add a time-based holdout and compare any forecasting model against a simple historical baseline. Label historical heatmaps and forecasts separately.
2. Add admin map layers using the existing Google Map component: incident pins (restricted), density heatmap, and forecast hotspots with time horizon, sample count, and uncertainty. Provide a list/table alternative.
3. Compute resolution metrics server-side from status events: median and percentile time from report/assignment to resolution, backlog age, reopen rate, and counts by area/category/date. Define treatment of rejected, unresolved, and legacy rows. Use date and team filters consistently across chart, table, CSV, and PDF.
4. Extend the transactional outbox for citizen events (accepted/rejected, assigned, in progress, resolved, reopened), with delivery state and retries. Offer an in-app notification history; email remains dependent on configured delivery SMTP. Keep recipient consent/preference and private links.
5. Add privileged server-side CSV and PDF exports with filters, generation timestamp, data provenance, row counts, safe spreadsheet cell escaping, and export audit. Cover large result sets with streaming/background generation and expiration as appropriate.

**Gate:** forecast beats or is honestly labeled against baseline; heatmap respects privacy thresholds; metrics reconcile to event rows; export fields/counts match filtered API; formula-injection tests pass; notifications work with a configured staging sender and failures remain visible.

## Phase 5 — deployment rehearsal and acceptance

Run migration and the full role workflow against a disposable staging copy. Verify Supabase RLS/Storage policies, signed assets, model fallbacks, email behavior, map key restrictions, Tunnel HTTPS routing, backups, and restore. Run the existing backend/frontend suites and add targeted tests for the new contracts; report actual commands and outcomes at that time. Rehearse the laptop demo with a phone on mobile data and a network interruption. Document that the laptop must remain powered and that model inference may be slow or unavailable. Obtain rubric sign-off against all eight matrix rows before calling CSP650 complete.

## Suggested implementation order and dependencies

`Data contract + backup → Supabase schema/RLS/Storage → staff authorization → workflow/proof → calibrated AI fields → aggregation/forecast → metrics/notifications/exports → rehearsal`.

The dependency order matters: analytics and export must read the authoritative migrated store; staff endpoints need trusted roles and RLS; percentages require evaluation before presentation. Parallel UI mockups are safe once the data contracts are fixed. Keep existing local AI services and Tunnel for the demo unless deployment constraints change.
