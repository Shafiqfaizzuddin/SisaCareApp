# SisaCare.AI

SisaCare.AI is an AI assisted community waste reporting prototype for residents and municipal administrators. It does not claim a partnership with a particular authority. Community users submit and track reports; authorized municipal administrators verify, reject, assign, and resolve them.

## Stack and workflow

- React, TypeScript, and Vite frontend; FastAPI and SQLite backend; Supabase Authentication.
- Selecting a photo sends it through the authenticated backend to local Florence-2. The backend applies waste rules to candidate objects, then requests an editable draft from local Ollama. A factual template is used if Ollama is unavailable. Analysis and drafting do not require a map or location.
- The user can optionally expand **Edit analysis / Add details** to correct detections, materials, categories, or quantities. Uncertain items remain marked **Needs Confirmation** and can be sent for admin assessment. The user then confirms one incident pin, reviews the draft, and submits it. Submission does not independently verify AI details; admin verification is separate.
- Equivalent detections are grouped for the analysis summary and report draft using canonical rule identity, material, category, uncertainty, and handling answers. The displayed detection count is model output, not a verified object quantity. Raw detections, source IDs, boxes, and optional user-provided quantities remain separate in the audit record.
- Admin review follows Submitted → Verified → Assigned/In Progress → Resolved, or Rejected with a reason. Status changes have an audit trail. Historical records retain their original status and category.

## Local setup

Install Node.js and Python 3.11 or newer. In PowerShell:

```powershell
npm install
cd frontend
npm install
cd ..\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd ..
Copy-Item frontend\.env.example frontend\.env.local
Copy-Item backend\.env.example backend\.env
```

Set the Supabase URL and publishable key in both environment files, and the server side service role key and Google client ID in `backend/.env`. Configure the Google provider for Supabase and register local login redirect URLs. Admin access requires a reviewed `app_metadata.role=admin` grant; an email domain or user profile value never grants it. Existing website email/password login remains supported.

For Google sign-in, use the same Web OAuth client ID in `frontend/.env.local` (`VITE_GOOGLE_CLIENT_ID`) and `backend/.env` (`GOOGLE_CLIENT_ID`), then restart both development servers after changing either file. A rejected Google credential is logged by the backend with a reason code only; never copy the credential or ID token into logs or support messages.
Verified Google accounts from any email domain can sign in as community users. In Google Cloud, the OAuth app audience must permit external users; an Internal audience or a Testing audience limited to named test users can still block other Google accounts before they reach this application. Configure the authorized JavaScript origins for each deployed site and development URL. Existing password accounts with the same email must sign in and link Google from their account page; the app does not merge accounts by email alone. The backend accepts a verified, matching Google provider email when Supabase has not populated its separate email-confirmation timestamp.

Email/password signup uses Supabase's confirmation email and redirects back to `/login`. Keep **Confirm email** enabled in the hosted Supabase project's Auth settings; `supabase/config.toml` enables it for local development. The branded confirmation email is in `supabase/templates/confirmation.html` and is wired into the local CLI config. For a hosted project, paste that HTML and its subject into Authentication → Email Templates → Confirm signup, allow the deployed `/login` URL in Auth redirect settings, and configure a production SMTP provider. Supabase's default mail service can restrict recipients and is unsuitable for public signup. Google accounts with an already verified provider email sign in through Google and do not need a second email confirmation message.
The server allows 30 seconds of Google token clock skew. If `google_id_token_rejected reason=clock_skew` persists, compare the logged `ahead_seconds` with the server's UTC clock and synchronize the server clock; do not increase the allowance to cover a badly misconfigured clock.

For maps, set `VITE_GOOGLE_MAPS_API_KEY` and `VITE_GOOGLE_MAP_ID` in `frontend/.env.local`. Restrict the browser key to the app's origins and the Maps JavaScript, Places, and Geocoding APIs. There is no campus boundary or assumed municipal jurisdiction. Reporting requires a confirmed incident pin; photo analysis works without maps.

Configure the isolated local Florence-2 service using [its README](florence_service/README.md). The backend calls it on the server side. Configure local Ollama URL and model in `backend/.env`; report drafting has a template fallback. YOLO weights and evaluation results are retained for historical comparison but are not part of the active analysis path.

The active community waste policy lives in `ai/config/waste_rules.json` (version 2.0.0). Specific Florence labels map automatically. Generic or unmapped detections and furniture whose discarded status is unclear use a separate local image model with the original photo and a padded crop. The installed `llama3.2` reporting model accepts text only, so set `OLLAMA_VISION_MODEL=qwen2.5vl:3b` in `backend/.env` after `ollama pull qwen2.5vl:3b` (about 3.2 GB). The model requires Ollama 0.6 or newer and available GPU or RAM capacity. If it is missing or returns invalid output, analysis shows a retryable error; it does not assign a default category. Report drafting still uses the configured local `OLLAMA_REPORT_MODEL` and a factual template if drafting fails. Category mapping is distinct from any station's material acceptance, and categories are application handling classes rather than legal waste codes. Historical analysis and report rows retain their original rules and labels.

Run the three processes in separate terminals:

```powershell
# Frontend
cd frontend
npm run dev
```

```powershell
# API
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Start Florence-2 as described in its README, then start local Ollama with the configured model. The frontend is normally at `http://localhost:5173`; the API is at `http://localhost:8000` and has docs at `/docs`.

## Migration and retention

Read [community migration decisions](docs/community-migration.md) before deployment. The schema changes are additive. Existing user IDs, reports, images, recycling actions, reward events, matric and E-Merit history remain stored. New community reports and legacy action reviews issue no Eco Points or E-Merit claims. Public station listings require explicit review through `public_verified`; old campus and demo stations are not automatically presented as municipal facilities. Live admin role grants must be reviewed by an authorized operator before any account permission migration.

## Checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
cd ..\frontend
npm run build
npm test
```

Browser session cookies have server side idle and absolute limits (`SESSION_IDLE_SECONDS`, default 3600; `SESSION_ABSOLUTE_SECONDS`, default 43200). While a signed-in page is visible and the person has recently interacted with it, the browser checks the session every five minutes so active form work refreshes the idle limit. An idle or hidden page does not keep the session alive, and the absolute limit still ends it. Browser closure cannot be detected reliably when a browser restores session state; explicit sign out invalidates the server session. If Google Identity Services fails to load after expiry, the sign-in page shows a retry control instead of an empty button area.
