# Phase 6 integration and regression test report

Run date: 2026-11-04. Scope: the current SisaCare.AI working tree. **No live three-account, browser, Supabase PostgreSQL, Google OAuth, Florence-2, Ollama, Cloudflare Tunnel, or real SMTP delivery run was performed.** Automated API tests use temporary SQLite and mocked identities, model responses, and email delivery. Synthetic forecasts are labeled separately from real reports. “Passed” below means the named controlled check actually ran, not that the entire production journey was verified.

**Manually verified results: none.** All successful checks in this report were automated or a reproducible command-line demonstration; live acceptance remains blocked by the dedicated test identities and environment described below.

## Executed commands and results

| Command | Result | Meaning |
| --- | --- | --- |
| `backend/.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --disable-warnings` from `backend` | **426 passed, 3 failed, 1 warning** (final rerun; see failures below) | Full backend regression suite, local test dependencies |
| `backend/.venv/Scripts/python.exe -m pytest tests/test_phase6_system.py tests/test_auth.py tests/test_csp650_phase2.py tests/test_phase5_notifications.py tests/test_admin_analytics.py tests/test_hotspots.py -q -p no:cacheprovider --disable-warnings` | **41 passed, 1 warning** before the later outage and expired-token cases | Focused cross-role, authorization, notification, analytics and forecasting coverage |
| `backend/.venv/Scripts/python.exe -m pytest tests/test_phase6_system.py -q -p no:cacheprovider --disable-warnings` | **2 passed, 1 warning** | New controlled journey and database outage cleanup |
| `npm test -- --run` from `frontend` | **79 passed in 26 files** | Component and page integration tests with happy-dom and mocked APIs |
| `npm run build` from `frontend` | **Passed** | TypeScript and production bundle. Vite warned about a bundle over 500 kB. |
| `npm run lint` from `frontend` | **Passed with 2 warnings** | Existing `react-hooks/exhaustive-deps` warnings in `RoleContext.tsx` and `GoogleMap.tsx`. |
| `backend/.venv/Scripts/python.exe scripts/train_hotspots.py --synthetic-demo --as-of 2026-11-02T00:00:00+00:00 --output-db <temporary>/demo.db --artifact <temporary>/demo.joblib` | **Completed; status `available`** | 665 isolated synthetic records, four forecast periods, demo database and model artifact created outside the repository. |

The Vitest run emitted an `ECONNREFUSED` console message for `localhost:3000`; its process exited 0 and all 79 assertions passed. This message should be investigated if the frontend test environment is expected to run with a local API. The backend warning was suppressed in detail by `--disable-warnings`; it is not counted as a failure.

## Requested end-to-end journey

| Step | Status | Evidence and limit |
| --- | --- | --- |
| 1. Register citizen by email/password | **Passed in mocked frontend test; live blocked** | `RoleContext.test.tsx` tests sign-up/verification request. No test mailbox or live Supabase account was used. |
| 2. Authenticate using Google | **Passed in mocked frontend/backend tests; live blocked** | `UserLoginPage.test.tsx`, `google.test.ts`, `test_google_login_api.py`; no real Google browser consent flow was run. |
| 3. Upload waste image | **Passed in controlled API/UI tests** | `test_phase6_system.py` submits a small fixture PNG; `SubmitReportPage.test.tsx` uploads a file in happy-dom. This does not establish real object storage upload. |
| 4. Florence-2 classification and review | **Passed with controlled model output; local model blocked** | `test_florence_analysis_api.py`, `test_classification_summary.py`, and `SubmitReportPage.test.tsx` exercise evidence counts, distribution, severity and uncertainty. No local Florence inference timing or accuracy was measured. |
| 5. Edit generated description | **Passed in frontend test** | The new report-page test checks the citizen edit in the submitted payload; model drafting was mocked. |
| 6. Choose map location and submit | **Passed in controlled UI/API tests** | Report-page test chooses a stub map pin; API journey submits valid coordinates. Real Google Maps interaction was not run. |
| 7. Verify persistence and image access | **Passed for temporary SQLite; Supabase blocked** | API journey reads back report status, description and coordinates. Existing `test_csp650_phase1.py` checks private storage authorization with mocks. No live PostgreSQL row or Supabase Storage object was inspected. |
| 8. Admin assigns staff | **Passed in controlled API test** | Server-granted staff identity and assignment endpoint exercised; other Phase 2 tests deny unauthorized grants. |
| 9. Staff starts and submits cleanup proof | **Passed in controlled API/UI tests** | API journey runs both transitions with a PNG. New `StaffTaskDetailPage.test.tsx` checks form gating and calls. |
| 10. Admin verifies resolution | **Passed in controlled API test** | Verify endpoint returns 200 after proof; Phase 2 tests cover rework and conflicting transitions. |
| 11. Citizen sees timeline | **Passed at API level; browser view blocked** | Citizen detail response contains assigned, in-progress, pending-verification and resolved events in order. No real browser refresh was run. |
| 12. Resolution email queued and delivered | **Passed with mocked SMTP; real delivery blocked** | API journey dispatches and sees a sent outbox event; `test_phase5_notifications.py` checks retry and SMTP outage. No provider inbox receipt was verified. |
| 13. Historical analytics contribution | **Passed in controlled API test** | One submitted and one verified resolution counted; analytics fixtures cover filters, nulls and resolution metrics. Live aggregate was not queried. |
| 14. CSV and PDF exports | **Passed at API level** | Both admin endpoints returned success; PDF bytes began `%PDF`. Dedicated analytics tests check content, filtering and authorization. No visual PDF review was performed. |
| 15. Train/evaluate model and dashboard | **Passed with synthetic data; production blocked** | Reproducible demo training generated four periods and model metadata. `test_hotspots.py` covers load/checksum, leakage, insufficient data and endpoint authorization; admin dashboard test checks separate forecast layer. Real history remains insufficient per `CSP650_HOTSPOT_ANALYTICS.md`; no production forecast claim is made. |

## Negative and reliability checks

| Requirement | Status | Evidence and limit |
| --- | --- | --- |
| Invalid and expired Supabase tokens | **Passed with mocked Supabase response** | `test_auth.py` checks provider 401, including an expired-token message, with generic client error. Live token expiry was not exercised. |
| Unauthorized roles and staff ownership | **Passed in API tests** | `test_csp650_phase2.py`, `test_admin_analytics.py`, `test_hotspots.py` cover citizen/staff/admin denial paths, wrong owner and revoked grants. |
| Missing, invalid and oversized images | **Partially passed** | API journey rejects invalid MIME; `test_reports_api.py` rejects missing photo; Phase 2 tests reject invalid cleanup uploads. Image size validation has existing unit coverage; no live large-image transfer was run. |
| Duplicate submission and competing transitions | **Passed in API tests** | `test_reports_api.py` checks draft reuse; `test_csp650_phase2.py` checks concurrent assignment and stale transitions. |
| Database outage | **Passed in controlled API test** | New test forces SQLite connection failure, receives HTTP 500 with generic message and confirms temporary upload removal. PostgreSQL outage/recovery was not run. |
| SMTP outage | **Passed with mocked failure** | `test_phase5_notifications.py` confirms valid transition persists and outbox retries remain visible. |
| Florence-2 and Ollama unavailable | **Passed with mocked failures** | Florence tests cover unavailable/timeout/partial results. Draft tests cover Ollama timeout and template fallback. Real process shutdown was not run. |
| Empty historical data | **Passed in forecasting and analytics tests** | Explicit unavailable/insufficient-data response and empty analytics fixtures. |
| Invalid coordinates | **Passed in API tests** | `test_reports_api.py` rejects out-of-range locations. |
| Private storage restrictions | **Passed with mocked storage** | Phase 1 tests check owner/admin image access and private cache headers; live Supabase bucket policy remains unverified. |
| Mobile/desktop responsiveness | **Blocked for visual verification** | Signup test asserts responsive grid classes; no viewport screenshot or device/browser layout check was run. |
| Refresh, session persistence and navigation | **Partially passed** | `test_browser_session.py`, `RoleContext.test.tsx`, login and router tests cover cookie expiry, remount and route behavior. No live browser refresh with an actual Supabase session was run. |

## Full backend suite failures

1. `tests/test_google_identity.py::test_matric_from_verified_email_does_not_replace_verified_value` expected automatic matric derivation from verified email; current `read_identity` returns no matric until explicit submission.
2. `tests/test_google_identity.py::test_matric_suggestion_requires_verified_email_and_student_eligibility_requires_admin_verification` has the same automatic-derivation expectation.
3. `tests/test_recycling_points_api.py::test_only_active_registered_production_points_are_recommended` expects an active production point to appear publicly without `public_verified=1`; the current endpoint requires public verification. `test_community_workflow.py` checks this gate.

These failures predate the Phase 6 test additions and remain **failed**, not waived. Resolve the identity product contract and update implementation or tests accordingly; explicitly mark test fixture points as publicly verified if the current reviewed-point policy is intended. The Phase 6 changes did not alter application behavior to conceal these failures.

## Live verification needed before acceptance

Use a non-production Supabase project and three dedicated test accounts with server-side citizen/staff/admin grants. Configure isolated PostgreSQL and private Storage migrations, Google OAuth redirect origins, a test mailbox/provider, and running Florence-2/Ollama services. Execute the 15-step journey in a desktop and mobile browser, including a hard refresh and session expiry. Inspect PostgreSQL rows, private Storage access as each role, the email outbox and received mailbox, analytics deltas, PDF rendering, and forecast provenance. Use test images and report records clearly marked for cleanup. Keep SMTP and service-role secrets server-side. No such live result is recorded in this report.

### Files added or changed for Phase 6

- `backend/tests/test_phase6_system.py`: controlled three-role API journey and database-outage cleanup.
- `backend/tests/test_auth.py`: expired provider-token response case.
- `frontend/src/pages/SubmitReportPage.test.tsx`: analysis review, citizen edit, map pin and submission payload integration.
- `frontend/src/pages/StaffTaskDetailPage.test.tsx`: staff progress and cleanup proof UI integration.
- `docs/CSP650_PHASE6_TEST_REPORT.md`: this report.
