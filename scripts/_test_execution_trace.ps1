# Test execution trace implementation
$job_body = @{
    source_dialect = "postgresql"
    target_dialect = "mysql"
    source_connection = @{
        host = "localhost"
        port = 5433
        username = "postgres"
        password = "postgres_dev_password"
        database = "sample_source"
        schema_name = "sample"
    }
    target_connection = @{
        host = "localhost"
        port = 3306
        username = "appuser"
        password = "mysql_dev_password"
        database = "sample_source"
        schema_name = ""
    }
}

Write-Host "Creating migration job..."
$job = Invoke-RestMethod -Uri "http://localhost:8000/jobs" -Method Post -Body ($job_body | ConvertTo-Json -Depth 10) -ContentType "application/json"
$job_id = $job.job_id
Write-Host "Created job: $job_id"

# Poll every 2 seconds and display execution trace
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 2
    $status = Invoke-RestMethod -Uri "http://localhost:8000/jobs/$job_id" -Method Get
    $trace_count = ($status.execution_trace | Measure-Object).Count
    
    Write-Host ("Poll $i`: Phase=$($status.current_phase), Trace steps=$trace_count")
    
    if ($trace_count -gt 0) {
        Write-Host "Latest steps:"
        $status.execution_trace | Select-Object -Last 3 | ForEach-Object {
            $icon = if ($_.status -eq "SUCCESS") { "[OK]" } elseif ($_.status -eq "FAILED") { "[ERR]" } else { "[RUN]" }
            Write-Host "  $icon $($_.phase): $($_.operation) - $($_.details)"
        }
    }
    
    if ($status.status -in @("DONE", "ABORTED", "ROLLED_BACK")) {
        Write-Host "Job completed with status: $($status.status)"
        break
    }
}

Write-Host "Test complete. Full trace:"
$status.execution_trace | ConvertTo-Json
