# SisaCare.AI

SisaCare.AI is a responsive illegal waste dumping reporting and municipal review
application. It uses React/Vite/TypeScript, FastAPI, and a live Supabase project
for authentication, PostgreSQL data, row-level security, and private report images.

The implemented workflow includes:

- Guest and registered-member report submission
- Private report image uploads and optional GPS coordinates
- Administrator validation and independent case-status history
- Idempotent reward transactions, achievements, titles, and live leaderboards
- Published educational content with administrator CRUD controls

YOLO and LLM inference remain optional future services. Reports retain the
reporter's selected category until an AI analysis is attached.

## Prerequisites

- Node.js with npm
- Python 3.11 or newer

## Install dependencies

Install the root Supabase CLI dependency:

```powershell
npm.cmd install
```

Install the frontend dependencies:

```powershell
cd frontend
npm.cmd install
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
Copy-Item frontend\.env.example frontend\.env.local
Copy-Item backend\.env.example backend\.env
```

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` using the browser-safe
values from the Supabase project settings. Never place a secret or service-role
key in a `VITE_` variable. Do not commit populated `.env` files.

Supabase Auth emails are configured to use Mailtrap SMTP. Copy `.env.example` to
`.env`, then set `MAILTRAP_SMTP_USER`, `MAILTRAP_SMTP_PASS`, and
`MAILTRAP_FROM_EMAIL`. For the hosted Supabase project, apply the same Mailtrap
SMTP values in Authentication > Emails > SMTP settings so sign-up, invite,
magic-link, recovery, and email-change messages are sent through Mailtrap.

Apply pending database migrations after linking the CLI to the project:

```powershell
npx.cmd supabase link --project-ref your-project-ref
npx.cmd supabase db push
```

New email signups receive the `user` role. Administrator roles must be assigned
by a trusted operator in Supabase; the browser cannot promote an account.

For example, run this from the Supabase SQL Editor after replacing the email:

```sql
update public.profiles
set role = 'admin', title = 'Municipal Administrator'
where email = 'admin@example.com';
```

## Run locally

Start the frontend:

```powershell
cd frontend
npm.cmd run dev
```

In another terminal, start the backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`, with interactive documentation at
`http://localhost:8000/docs`. The health check is `GET /api/v1/health`.

## Verify the application

Run the backend test:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Build the frontend:

```powershell
cd frontend
npm.cmd run build
```

The frontend restores Supabase sessions automatically. New members may need to
confirm their email before their first sign-in, depending on the project's Auth
settings. Add each deployed frontend origin to Supabase Auth URL Configuration so
confirmation links return to `/login` correctly.
