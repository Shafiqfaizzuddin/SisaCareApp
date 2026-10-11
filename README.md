# SisaCare.AI

Initial project foundation for the SisaCare.AI illegal waste dumping reporting system.
This session includes a React/Vite/TypeScript frontend, a FastAPI backend with a
health endpoint, local AI analysis, SQLite-backed report submission, and
Supabase-authenticated member and administrator sessions.

## Prerequisites

- Node.js with npm
- Python 3.11 or newer

## Install dependencies

Install the root Supabase CLI dependency:

```powershell
npm install
```

Install the frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

Create the backend virtual environment and install the API and test dependencies:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cd ..
```

## Configure the environment

Copy the service-specific examples before running locally:

```powershell
Copy-Item frontend\.env.example frontend\.env
Copy-Item backend\.env.example backend\.env
```

The current examples contain no secrets. Do not commit populated `.env` files.

For waste-location support, configure:

- `TOMTOM_API_KEY` in `backend/.env` for Search and Reverse Geocoding.
- `VITE_TOMTOM_API_KEY` in `frontend/.env.local` for browser Map Display tiles.

The browser key is visible to map users by design. Create a separate TomTom key
for Map Display and, if your TomTom plan supports it, restrict it to your
local/production domains. Restrict the backend key to Search and Reverse
Geocoding where key controls are available. Neither key is logged by the application.

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` in
`frontend/.env.local`. Create member accounts in Supabase Authentication. Admin
accounts must have `app_metadata.role` set to `admin`; user-editable metadata is
not trusted for administrator access.

For a hosted Supabase project, add `http://localhost:5173/login` and
`http://127.0.0.1:5173/login` to Authentication > URL Configuration > Redirect
URLs so email confirmation returns to the local app.

## Run locally

Start the frontend:

```powershell
cd frontend
npm run dev
```

In another terminal, start the backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`, with interactive documentation at
`http://localhost:8000/docs`. The health check is `GET /api/v1/health`.

## Verify the foundation

Run the backend test:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Build the frontend:

```powershell
cd frontend
npm run build
```

Run the frontend location tests:

```powershell
cd frontend
npm test
```

Supabase CLI configuration is present in `supabase/config.toml`, and frontend
authentication uses the configured Supabase project.

## Authentication configuration

Email/password accounts remain in Supabase Auth. Existing users and password
hashes are not migrated. Keep email/password sign-up enabled and turn on
**Confirm Email** in the hosted Supabase project (the local config enables it).
Configure SMTP for production confirmation and reset emails. The app also
rejects unconfirmed sessions on protected API routes. Add the following exact
Supabase redirect URLs for each deployed frontend origin:

- `https://YOUR-FRONTEND/login` (email confirmation)
- `https://YOUR-FRONTEND/password-reset?mode=recovery` (password reset)
- `https://YOUR-FRONTEND/account` (email sign-in link for account recovery)

Include corresponding `http://localhost:5173` and `http://127.0.0.1:5173`
URLs for local development. Supabase redirect allow-list rules must include
these paths. The login pages retain email/password login; the reset link uses
Supabase's recovery email and `updateUser` flow. Logout uses Supabase `signOut`.

For Google sign-in, create a Google **Web application** client. Put its client
ID in `frontend/.env.local` as `VITE_GOOGLE_CLIENT_ID` and in `backend/.env`
as `GOOGLE_CLIENT_ID`. Put the Supabase service-role key only in `backend/.env`
as `SUPABASE_SERVICE_ROLE_KEY`; it is used for the existing-email precheck and
must never be included in frontend variables or logs. Enable Google in the
Supabase Auth provider settings with that client ID and its client secret.
For local Supabase CLI, export `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
from a private environment file before `supabase start`; `supabase/config.toml`
reads those variables. The secret is never used by the browser or FastAPI.

Add each frontend origin (for example `http://localhost:5173`) to the Google
client's **Authorized JavaScript origins**. The Google Identity Services button
returns an ID token to the browser; FastAPI verifies its signature, issuer,
audience, expiry, verified email, and exact normalized domain using
`google-auth` before Supabase `signInWithIdToken`. This button does not use a
Google redirect callback. For Supabase provider redirect flows, the callback is
`https://YOUR-PROJECT.supabase.co/auth/v1/callback` (local:
`http://127.0.0.1:54321/auth/v1/callback`); register it with Google if enabling
redirect-based linking separately. Enable **Allow manual linking** in Supabase
Auth settings for the signed-in account connection button.

First-time Google sign-in is limited to verified `uitm.edu.my` or
`student.uitm.edu.my` addresses. Returning Google users are matched by the
Google provider and stable subject in Supabase Auth, then signed into the
same participant account. The app also records that subject in its local
identity row after the authenticated Supabase session is checked. A repeated
login does not create another participant row or reset matric review data.
The Google button and any One Tap credential callback use this same flow.
Existing website users with the same email can sign in with their password
and connect Google from their account page. If they have no password, they
can request an email sign-in link from the collision message, then connect
Google while signed in. This requires working Supabase email delivery and an
account that can receive the link. An ambiguous old account with neither a
trusted matching Google subject nor a working email identity needs an
administrator-assisted recovery; matching email alone does not authorize a
Google identity link. Do not delete or recreate that account, since it may
own reports, reviews, and points.
Supabase Auth has automatic same-email identity linking by default; the API
precheck rejects a known existing email before first-time Google sign-in, but
there is a race between that check and Supabase session creation. Deployments
that need a strict guarantee against that race require an auth provider with
configurable automatic linking or a provider-level policy. Do not treat this
precheck as a transactional guarantee.

The repository sets `auth.enable_manual_linking = true` for local Supabase.
Also enable **Allow manual linking** in the hosted project's Auth settings;
local configuration does not change the hosted project. A read-only audit of
the connected SisaCare project found one Google-origin account with one Google
identity and no Google-origin account missing an identity. Its admin users
list omitted the identity, while admin user detail included `identity_data.sub`.
No account records were changed by that audit. Automated tests cover the
returning user and collision paths, but a real Google sign-in/logout/sign-in
sequence still needs valid Google credentials and a browser session.

Affiliation is separate from app permissions. New signups are ordinary
participants; only trusted Supabase `app_metadata.role = admin` grants the
existing Admin/Staff permission. Students and staff may declare their
affiliation, which stays `pending_verification` until a separate institutional
verification process approves it. A verified numeric prefix of a
`student.uitm.edu.my` email prefills the matric field, without marking the
matric as verified or overwriting a verified one. Other addresses require
manual matric entry for a student claim. The local `member_identities` SQLite
table stores the Google account's stable `sub`, claim, matric source, and
verification status; it does not store passwords or Google tokens.

## Matric review and E-Merit eligibility

The participant account page shows a suggested matric number from a verified
numeric `student.uitm.edu.my` prefix. The student can correct it before choosing
**Submit matric for verification**. A correction is recorded as self-reported.
The current states are Not Submitted, Pending, Verified, and Rejected. Rejected
students see the reason and can resubmit. Changing a verified number starts a
new review and blocks new E-Merit eligibility records until approval. A partial
unique index prevents two accounts from holding the same verified matric number.
Pending E-Merit requests tied to the old matric review are cancelled when the
verified number changes; their points become available again after reapproval.
Legacy verified flags without a reviewer audit are moved to Pending for a new
admin review when the identity table is migrated.
Changing the claim to staff revokes the current student verification and cancels
pending E-Merit eligibility records; prior review decisions stay in the audit table.

Authorized admins review pending submissions at `/admin/matric`. They must
record whether they checked an authorized student record or an agreed manual
procedure, what was checked, and a rejection reason when rejecting. The review
queue includes the authenticated email recorded at submission. In the absence
of an official UiTM data source, this is **prototype manual
verification**, not official enrolment validation. Email ownership and matric
extraction alone do not establish current UiTM Arau enrolment. Matric data is
returned only through the owner's protected identity API or the admin review
queue; those responses disable caching. No identity documents are uploaded.

Pending and rejected users can still report and earn internal points on approved
reports. Reports snapshot the participant's claimed affiliation at submission,
and reward events keep that snapshot when a report is approved. Staff and
unknown-classification activity points, including legacy events without a
snapshot, cannot become E-Merit eligible through a later profile edit. A
verified student can reserve 50 available student activity points for one
pending E-Merit eligibility record; institutional approval is still required.
New valid reports award 2 Eco Points. The recycling action table and 5-point
award constraints are ready for a later submission and admin review API;
institutional E-Merit approval integration is not yet in this repository.

## Campus database migration

The backend extends its existing SQLite database on initialization. Existing
`reports`, `analysis_drafts`, `waste_detections`, and `reward_events` rows are
preserved. Supabase Auth remains the source for login providers, verified email,
and password hashes; `member_identities` stores the Google subject, affiliation
claims, and matric status, while `matric_reviews` retains reviewer history.

`reports` now records the confirmed AI snapshot, review fields, data origin,
and an activity key. `recycling_points` holds registered locations and accepted
materials; `recycling_actions` holds selected points, original analysis/photo,
proof photo and location, and admin decision fields. No recycling points are
seeded. Future imports must mark example locations
and activity as `demo`; member reward totals and E-Merit calculations exclude
demo rewards.

`reward_events` is the signed Eco Point ledger. Its existing `points` column
remains for old queries; new rows also record `signed_amount`, transaction type,
source activity, affiliation snapshot, E-Merit classification, origin, and audit
reference. New report and recycling awards are constrained to 2 and 5 points,
respectively. A unique activity key prevents awarding both paths for the same
source photo. Submission code must use `sha256:<hex digest of original photo>`
for both paths, or a stable shared analysis identifier if no photo is available.
This identifies identical source data; it cannot prove that two different photos
show the same physical event.

Historical reward rows are marked `legacy_unclassified` and `legacy_unknown`;
they retain their internal points but do not become E-Merit eligible. Historical
report rows also receive `legacy_unknown` origin. The E-Merit table records a
50-point reservation for one E-Merit, the current verified matric review,
reviewer/decision fields, and a unique reservation reference. A database trigger
checks verified student status and available eligible points at reservation time.
No past reward is reclassified without a separate reviewed migration rule.

## Photo analysis and report location

Photo analysis accepts an authenticated user's validated image without
coordinates, GPS permission, a map provider, or a boundary configuration.
The participant chooses an incident location only when submitting a report.
The backend validates latitude and longitude ranges but imposes no campus
boundary. Existing report locations and submissions are unchanged.

The participant reviews each YOLO/VLM detection independently. The existing
material mapping determines known items' disposal categories; unknown items
require manual classification. A mixed image is not classified as wholly
recyclable. The original draft and detections remain separate from the saved
confirmed items and edited report text. New reports begin in `submitted`
status and earn no points until admin validation. Recyclable reports can use
the registered production recycling points for guidance.

## Nearby and registered recycling points

Authorized administrators manage points at `/admin/recycling-points`. Enter only
locations that staff have checked; this repository contains no seeded real
recycling point coordinates. The form stores name, WGS84 coordinates,
accepted material names, description, and active status in the existing
`recycling_points` table. Deactivation hides a point from recommendations and
retains its row and historical activity references. Demo rows remain excluded
from production APIs.

After analysis, **View nearby recycling points** asks for device location.
If permission is denied, the participant can search an area or select it on
the TomTom map. The backend calls [TomTom category search](https://docs.tomtom.com/search-api/documentation/search-service/category-search) for recycling POIs
within 20 km of that area and combines them with nearby registered points.
TomTom may have no listings in an area and does not supply confirmed accepted
materials for these results; the UI labels acceptance unknown and keeps those
listings visible. Registered points retain their admin supplied material list.
Only registered points can be selected for proof submission and Eco Points.
The app does not create a registered point from a TomTom listing.

When a participant chooses **Recycle It**, active registered points accepting at least
one confirmed recyclable material are shown. Each result identifies matching
and unmatched materials, and sorting uses current GPS when available or the
confirmed waste location as a labelled fallback. Displayed distances are
approximate straight-line distances. The existing TomTom map displays the
selected point; the **Show pedestrian route** button requests a route from
TomTom's [Routing API](https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route).
Routes depend on TomTom coverage and may be unavailable for some paths.
Set `VITE_TOMTOM_API_KEY` in `frontend/.env.local` to a browser-restricted
TomTom key with Maps and Routing access. No journey times are inferred.

## Recycling actions and review

After analysis, **Recycle It** lets a signed-in student or staff participant
select a registered point that accepts every confirmed material. At the point,
they upload one JPG, PNG, or WEBP proof photo (maximum 10 MB) and capture
current GPS or describe the proof location manually. Manual locations are
labelled as such. Photos and location support manual review; they do not
conclusively prove disposal. The server copies the original analysis photo
and proof into protected storage, saves the confirmed results and point, and
consumes the analysis draft atomically. Repeating the submission returns a
conflict. The account owner sees status and outcome in **Your recycling
actions** on the dashboard.

Administrators review pending actions at `/admin/recycling-reviews`. Verification
awards 5 internal Eco Points; rejection requires a reason and awards none.
Evidence cannot be changed after review. A shared activity key prevents an
original photo that already earned report or recycling points from earning
another award. If the same photo is submitted for another action, the
reviewer must reject that duplicate. Verified staff activity remains
ineligible for E-Merit.
