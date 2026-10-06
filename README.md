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
