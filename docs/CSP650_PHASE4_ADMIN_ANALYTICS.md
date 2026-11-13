# Phase 4: administrative analytics, maps, and exports

## Data scope and definitions

The backend reads the configured report database (SQLite locally or Supabase PostgreSQL through the existing adapter). Analytics default to `data_origin=production`. Administrators may explicitly switch to `legacy_unknown` or `demo`; these sources are never merged silently. Date filters are inclusive UTC **submission** dates, and category, current status, and fixed 0.05° grid area filters select one submitted-report cohort.

- **Total submitted:** number of reports in the selected cohort, regardless of current status.
- **By status/category:** current report status and saved report waste category for that cohort.
- **Resolution rate:** reports currently in `resolved` status divided by cohort submissions. Empty cohorts return `null`.
- **Verified resolution duration:** time from original submission to a `pending_verification` to `resolved` status-history event for a report still resolved. Average and median use only these durations. Older direct resolutions and records without that event are counted separately and excluded from timing, never given an invented verification timestamp.
- **Trends:** daily submitted counts for the selected cohort and daily verified-resolved event counts for that cohort. A resolution can fall after the selected submission end date. The dashboard shows the latest 30 dates; the PDF chart and table show the latest 12.
- **Staff tasks:** assignment rows attached to the cohort, active assignments with no end time, and verified completions with cleanup proof attached to an assignment. Reassignment/ended tasks without proof are not treated as completed. Per-staff counts use the trusted staff UUID, abbreviated in the dashboard.
- **Observed map:** submitted-report counts in fixed 1,000 m Web Mercator cells, rendered from server-returned cell boundaries. At Malaysian latitudes the ground width is close to 1 km; projected metres are not exact ground metres at every latitude. Missing, invalid, or out-of-projection coordinates are omitted from the map and counted separately. The map does not send exact report coordinates or reporter names to the browser. Admins can see one-report cells; do not reuse this density response for a public map without a separate privacy threshold or broader aggregation.

The forecast layer comes from the existing versioned hotspot endpoint and retains its separate 0.05° cells; it is not rescaled into 1 km squares. Its predictions are for incident **report counts**, not waste volume. The model was trained across all categories, so category, status, submission-date, and observed-area filters do not apply to forecasts. The dashboard labels this difference and separates `synthetic_demo` forecasts from observed production or demonstration reports. Synthetic forecasts come from a reproducible dataset separate from observed demonstration reports. The observed legend uses fixed count bands (1, 2, 3–4, 5–9, 10+); color is report frequency within the selected filters, never a likelihood-times-severity risk score.

The admin map displays each observed count as a clickable badge at its aggregated cell center. Clicking a badge pans and zooms to that cell; observed badges also select its count details. Forecast badges focus their larger forecast cell and show approximate predicted counts to one decimal place (or less than 0.1). Cell centers represent aggregated areas, not exact incident coordinates. "Find my location" requests browser geolocation only when clicked, pans to the device location, and displays a temporary blue marker; it does not write coordinates to a report or send them to the backend. Permission denial, timeout, and unavailable location are visible. "Show all areas" restores the data view. The table remains the keyboard-accessible way to inspect cell counts.

## APIs

All routes require the existing authenticated administrator dependency; citizens, staff, and unauthenticated callers cannot read them.

| Route | Purpose |
| --- | --- |
| `GET /api/admin/analytics` | Metrics, trends, aggregated observed heatmap and source/filter metadata. |
| `GET /api/admin/analytics/export.csv` | Filtered safe report rows, UTF-8 CSV. |
| `GET /api/admin/analytics/export.pdf` | Formatted aggregate report with filter range, UTC generation timestamp, metrics, definitions, chart, tables and data-quality counts. |
| `GET /api/admin/hotspots/forecasts` | Existing saved forecast endpoint used as a distinct modeled map layer. |

Analytics endpoints accept `start=YYYY-MM-DD`, `end=YYYY-MM-DD`, `category`, `status`, `area=g1km:<x-index>:<y-index>`, and `provenance=production|legacy_unknown|demo`. The observed map response contains cell key, center, south/north/west/east bounds, and count. An inverted date range or old `g005` area key returns 422. Existing saved forecast keys remain `g005`. Responses are built in the backend; the browser does not calculate authoritative metrics or build exports from the recent-report list.

CSV columns are explicitly limited to `reference`, `category`, `status`, `submitted_at`, `area`, and `verified_resolved_at`. The export excludes reporter names, emails, contact details, free-text descriptions, street addresses, and exact coordinates. Values beginning with spreadsheet formula operators (including after leading whitespace) are prefixed with a single quote before CSV encoding. CSV and PDF responses use `private, no-store` and download headers.

## Setup and verification

Install the updated backend dependencies with `pip install -e '.[dev,analytics]'` from `backend`; `reportlab` is a required backend dependency and `pypdf` is used by export tests. The existing Google Maps API key and map ID are needed for the dashboard map. No new database migration or frontend secret is required for Phase 4. The report, status-event, assignment, and cleanup-proof tables must have the existing Phase 1/2 schema.

```powershell
cd backend
python -m pytest tests/test_admin_analytics.py tests/test_hotspots.py
cd ../frontend
npm test -- --run src/pages/AdminDashboardPage.test.tsx src/components/location/GoogleMap.test.tsx
npm run build
```

The fixture verifies four reports: three currently resolved, two with verified events at 24 and 72 hours, one resolved without a verification event, and one unresolved without coordinates. Expected resolution rate is 75%; verified average and median are both 48 hours. Three assignment records include one active task and one verified completion with cleanup proof. Tests also cover date/category/area filters, empty results, formula-like CSV values, PDF content, and admin authorization.
