# Start API with automatic destination DB cleanup
# Usage: .\scripts\Start-API-Clean.ps1 [-FullReset]

param(
    [switch]$FullReset
)

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

Write-Host "[Startup] Resetting sample databases..." -ForegroundColor Cyan
if ($FullReset) {
    & "$scriptDir\Reset-Sample-DBs.ps1"
} else {
    & "$scriptDir\Reset-Sample-DBs.ps1" -SkipOracle
}

Write-Host "[Startup] Starting FastAPI server...`n" -ForegroundColor Cyan

cd "$repoRoot\apps\api-fastapi"
poetry run uvicorn main:app --host 0.0.0.0 --port 8000
