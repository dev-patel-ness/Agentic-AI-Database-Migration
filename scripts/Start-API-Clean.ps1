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

Write-Host "[Startup] Dropping old foreign key constraints..." -ForegroundColor Cyan

# Drop any old FK constraints from seed data to prevent migration conflicts
$dropFkSql = @"
ALTER TABLE sample.project_assignments DROP CONSTRAINT IF EXISTS sys_c008238 CASCADE;
ALTER TABLE sample.project_assignments DROP CONSTRAINT IF EXISTS sys_c008239 CASCADE;
ALTER TABLE sample.projects DROP CONSTRAINT IF EXISTS sys_c008233 CASCADE;
ALTER TABLE sample.employees DROP CONSTRAINT IF EXISTS sys_c008227 CASCADE;
ALTER TABLE sample.departments DROP CONSTRAINT IF EXISTS fk_departments_manager CASCADE;
"@

$tempFkFile = "drop_fk_startup.sql"
$dropFkSql | Out-File -FilePath $tempFkFile -Encoding UTF8 -Force
docker cp $tempFkFile postgres-sample:/tmp/drop_fk_startup.sql 2>&1 | Out-Null
$fkResult = docker exec postgres-sample psql -U postgres -d sample_source -f /tmp/drop_fk_startup.sql 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Old foreign key constraints cleared" -ForegroundColor Green
} else {
    Write-Host "⚠️  Warning: FK cleanup may have failed (this is usually safe to ignore)" -ForegroundColor Yellow
}

Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue
Remove-Item -Path $tempFkFile -Force -ErrorAction SilentlyContinue

Write-Host "[Startup] Starting FastAPI server...`n" -ForegroundColor Cyan

# Get the script's parent directory (repo root) and navigate there
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

cd "$repoRoot\apps\api-fastapi"
poetry run uvicorn main:app --host 0.0.0.0 --port 8000
