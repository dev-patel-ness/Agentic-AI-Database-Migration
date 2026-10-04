# Resets mysql-sample, postgres-sample ("sample" schema), and oracle-sample
# ("sample_user" schema) back to the canonical state defined by
# infra/docker/*-sample-init.sql. Run this between migration test rounds so
# leftover objects/rows from a previous job's target don't pollute the next
# job's discovery/object catalog (see docs/challenges-and-fixes.md).
# Usage: .\scripts\Reset-Sample-DBs.ps1 [-SkipOracle]

param(
    [switch]$SkipOracle
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$dockerDir = Join-Path $repoRoot "infra\docker"

Write-Host "[Reset] postgres-sample: dropping + recreating 'sample' schema..." -ForegroundColor Cyan
docker exec postgres-sample psql -U postgres -d sample_source -c "DROP SCHEMA IF EXISTS sample CASCADE;" | Out-Null
Get-Content (Join-Path $dockerDir "postgres-sample-init.sql") -Raw | docker exec -i postgres-sample psql -U postgres -d sample_source | Out-Null
Write-Host "postgres-sample reset" -ForegroundColor Green

Write-Host "[Reset] mysql-sample: dropping + recreating 'sample_source' database..." -ForegroundColor Cyan
docker exec mysql-sample mysql -uroot -pmysql_root_dev_password -e "DROP DATABASE IF EXISTS sample_source; CREATE DATABASE sample_source;" 2>$null | Out-Null
Get-Content (Join-Path $dockerDir "mysql-sample-init.sql") -Raw | docker exec -i mysql-sample mysql -uroot -pmysql_root_dev_password 2>$null | Out-Null
Write-Host "mysql-sample reset" -ForegroundColor Green

if ($SkipOracle) {
    Write-Host "[Reset] Skipping oracle-sample (-SkipOracle)" -ForegroundColor Yellow
} else {
    Write-Host "[Reset] oracle-sample: dropping + recreating 'sample_user' schema (can take a minute)..." -ForegroundColor Cyan

    $dropUserSql = @"
ALTER SESSION SET CONTAINER = XEPDB1;
BEGIN
    EXECUTE IMMEDIATE 'DROP USER sample_user CASCADE';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -1918 THEN RAISE; END IF; -- -1918: user does not exist
END;
/
"@
    $tempFile = Join-Path $env:TEMP "oracle_drop_user.sql"
    $dropUserSql | Out-File -FilePath $tempFile -Encoding ASCII -Force
    docker cp $tempFile oracle-sample:/tmp/oracle_drop_user.sql | Out-Null
    docker exec oracle-sample bash -c "sqlplus -s sys/oracle_dev_password@//localhost:1521/XE as sysdba @/tmp/oracle_drop_user.sql"
    Remove-Item -Path $tempFile -Force -ErrorAction SilentlyContinue

    docker cp (Join-Path $dockerDir "oracle-sample-init.sql") oracle-sample:/tmp/oracle-sample-init.sql | Out-Null
    docker exec oracle-sample bash -c "sqlplus -s sys/oracle_dev_password@//localhost:1521/XE as sysdba @/tmp/oracle-sample-init.sql"

    docker cp (Join-Path $dockerDir "oracle-sample-extra-objects.sql") oracle-sample:/tmp/oracle-sample-extra-objects.sql | Out-Null
    docker exec oracle-sample bash -c "sqlplus -s sys/oracle_dev_password@//localhost:1521/XE as sysdba @/tmp/oracle-sample-extra-objects.sql"

    Write-Host "oracle-sample reset" -ForegroundColor Green
}

Write-Host "`nAll sample databases reset to clean baseline." -ForegroundColor Green
