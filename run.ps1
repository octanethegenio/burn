$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

if (-not (Test-Path "web\node_modules")) {
    Push-Location web
    npm ci
    Pop-Location
}

Push-Location web
npm run build
Pop-Location

.\.venv\Scripts\python.exe -m server.launcher
