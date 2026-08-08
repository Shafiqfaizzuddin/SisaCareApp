# SisaCare.AI

Initial project foundation for the SisaCare.AI illegal waste dumping reporting system.
This session includes a React/Vite/TypeScript frontend, a FastAPI backend with a
health endpoint, and local Supabase CLI configuration only. Application-level
Supabase integration, authentication, AI models, and report submission are not
implemented yet.

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

Supabase CLI configuration is present in `supabase/config.toml`, but Supabase is not
connected to the application in this foundation.
