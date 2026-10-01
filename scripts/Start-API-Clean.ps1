# Start API with automatic destination DB cleanup
# Usage: .\scripts\Start-API-Clean.ps1

$ErrorActionPreference = "Continue"

Write-Host "[Startup] Truncating target database tables..." -ForegroundColor Cyan

# Create truncate SQL
$truncateSql = @"
TRUNCATE TABLE sample."DEPARTMENTS" CASCADE;
TRUNCATE TABLE sample."EMPLOYEES" CASCADE;
TRUNCATE TABLE sample."PROJECTS" CASCADE;
TRUNCATE TABLE sample."PROJECT_ASSIGNMENTS" CASCADE;
"@

# Write to temp file and execute
$tempFile = "truncate_startup.sql"
$truncateSql | Out-File -FilePath $tempFile -Encoding UTF8 -Force
docker cp $tempFile postgres-sample:/tmp/truncate_startup.sql 2>&1 | Out-Null
$result = docker exec postgres-sample psql -U postgres -d sample_source -f /tmp/truncate_startup.sql 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Target database truncated successfully" -ForegroundColor Green
} else {
    Write-Host "⚠️  Warning: truncate may have failed" -ForegroundColor Yellow
    Write-Host $result
}

Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue

Write-Host "[Startup] Starting FastAPI server...`n" -ForegroundColor Cyan
cd "apps\api-fastapi"
poetry run uvicorn main:app --host 0.0.0.0 --port 8000
