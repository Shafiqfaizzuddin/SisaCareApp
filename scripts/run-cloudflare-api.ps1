$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$frontendIndex = Join-Path $projectRoot 'frontend\dist\index.html'
$python = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $frontendIndex)) {
    throw 'Build the frontend first: cd frontend; npm run build'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'The backend virtual environment is missing. Follow the local setup in README.md.'
}

$env:APP_ENV = 'production'
$env:SERVE_FRONTEND = 'true'
$env:SESSION_COOKIE_SECURE = 'true'
$env:EMAIL_PUBLIC_BASE_URL = 'https://sisacare.online'
$env:CORS_ALLOWED_ORIGINS = 'https://sisacare.online'

Set-Location -LiteralPath (Join-Path $projectRoot 'backend')
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
