$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $projectRoot 'backend/.runtime'
$backend = Join-Path $projectRoot 'backend'
$florencePython = Join-Path $projectRoot 'florence_service/.venv/Scripts/python.exe'
$backendPython = Join-Path $backend '.venv/Scripts/python.exe'
$cloudflared = Join-Path $runtime 'cloudflared.exe'
$tunnelTokenFile = Join-Path $runtime 'cloudflare-token.txt'
$frontendIndex = Join-Path $projectRoot 'frontend/dist/index.html'
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source

foreach ($required in @($florencePython, $backendPython, $cloudflared, $tunnelTokenFile, $frontendIndex)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required demo file is missing: $required" }
}
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function Test-ListeningPort([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Start-HiddenService([string]$name, [string]$file, [string[]]$arguments, [string]$workingDirectory) {
    $process = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $workingDirectory `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime "$name.out.log") `
        -RedirectStandardError (Join-Path $runtime "$name.err.log") -PassThru
    Write-Output "$name started (PID $($process.Id))"
}

if (-not (Test-ListeningPort 8765)) {
    Start-HiddenService 'florence' $florencePython @('-m', 'florence_service.run') $projectRoot
} else { Write-Output 'Florence-2 already listening on port 8765' }

if ($ollama -and -not (Test-ListeningPort 11434)) {
    Start-HiddenService 'ollama' $ollama @('serve') $projectRoot
} elseif (Test-ListeningPort 11434) { Write-Output 'Ollama already listening on port 11434' }
else { Write-Warning 'Ollama was not found on PATH; report drafts will use the factual template.' }

if (-not (Test-ListeningPort 8000)) {
    $env:APP_ENV = 'production'
    $env:SERVE_FRONTEND = 'true'
    $env:SESSION_COOKIE_SECURE = 'true'
    $env:EMAIL_PUBLIC_BASE_URL = 'https://sisacare.online'
    $env:CORS_ALLOWED_ORIGINS = 'https://sisacare.online'
    Start-HiddenService 'backend' $backendPython @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1') $backend
} else { Write-Output 'SisaCare backend already listening on port 8000' }

$pidFile = Join-Path $runtime 'cloudflared.pid'
$tunnelRunning = $false
if (Test-Path -LiteralPath $pidFile) {
    $savedPid = 0
    if ([int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$savedPid)) {
        $tunnelRunning = [bool](Get-Process -Id $savedPid -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -eq 'cloudflared' })
    }
}
if (-not $tunnelRunning) {
    $process = Start-Process -FilePath $cloudflared -ArgumentList @('tunnel', 'run', '--token-file', $tunnelTokenFile) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtime 'cloudflared.out.log') `
        -RedirectStandardError (Join-Path $runtime 'cloudflared.err.log') -PassThru
    Set-Content -LiteralPath $pidFile -Value $process.Id
    Write-Output "Cloudflare Tunnel started (PID $($process.Id))"
} else { Write-Output 'Cloudflare Tunnel already running' }

Write-Output 'Check https://sisacare.online/api/v1/health after the services finish starting.'
