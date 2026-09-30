# Downloads the 3 JDBC driver jars + the connector-jdbc plugin jar needed by
# the seatunnel Docker image (infra/docker/seatunnel/Dockerfile COPYs
# jars/*.jar into /opt/seatunnel/lib and connectors/*.jar into
# /opt/seatunnel/connectors). Not committed to git -- each vendor has
# different redistribution terms. Run once before `docker compose build seatunnel`.
#
# NOTE: apache/seatunnel:2.3.9's bundled bin/install-plugin.sh shells out to
# a `mvnw` wrapper that doesn't exist in the published Docker image (only in
# the source distribution) -- `RUN bin/install-plugin.sh` silently fails
# there, so connector-jdbc is fetched directly from Maven Central instead.

$ErrorActionPreference = "Stop"
$jarsDir = Join-Path $PSScriptRoot "jars"
$connectorsDir = Join-Path $PSScriptRoot "connectors"
New-Item -ItemType Directory -Force -Path $jarsDir | Out-Null
New-Item -ItemType Directory -Force -Path $connectorsDir | Out-Null

$drivers = @(
    @{ Url = "https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar"; File = "postgresql-42.7.4.jar"; Dir = $jarsDir },
    @{ Url = "https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/8.4.0/mysql-connector-j-8.4.0.jar"; File = "mysql-connector-j-8.4.0.jar"; Dir = $jarsDir },
    @{ Url = "https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc11/23.5.0.24.07/ojdbc11-23.5.0.24.07.jar"; File = "ojdbc11-23.5.0.24.07.jar"; Dir = $jarsDir },
    @{ Url = "https://repo1.maven.org/maven2/org/apache/seatunnel/connector-jdbc/2.3.9/connector-jdbc-2.3.9.jar"; File = "connector-jdbc-2.3.9.jar"; Dir = $connectorsDir }
)

foreach ($driver in $drivers) {
    $dest = Join-Path $driver.Dir $driver.File
    if (Test-Path $dest) {
        Write-Host "Already have $($driver.File)"
        continue
    }
    Write-Host "Downloading $($driver.File) ..."
    Invoke-WebRequest -Uri $driver.Url -OutFile $dest
}

Write-Host "JDBC driver + connector jars ready in $jarsDir and $connectorsDir"
