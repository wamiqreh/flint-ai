# Integration smoke script: bring up docker-compose, start API, submit a task, then tear down
$compose = "docker-compose.integration.yml"
# Start services
Write-Output "Starting docker-compose services..."
docker-compose -f $compose up -d
# Wait for Postgres
Write-Output "Waiting for Postgres to be ready..."
for ($i=0; $i -lt 60; $i++) {
    try {
        docker-compose -f $compose exec -T postgres pg_isready -U postgres | Out-String | Write-Output
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
# Wait for Redis
Write-Output "Waiting for Redis..."
for ($i=0; $i -lt 30; $i++) {
    try {
        docker-compose -f $compose exec -T redis redis-cli ping | Out-String | Write-Output
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
# Start API
$env:USE_INMEMORY_QUEUE='false'
$env:POSTGRES__CONNECTIONSTRING='Host=postgres;Port=5432;Username=postgres;Password=postgres;Database=orchestrator'
$env:REDIS__ENDPOINT='redis:6379'
$env:ASPNETCORE_URLS='http://0.0.0.0:5156'
$out='api_integration_out.log'
$err='api_integration_err.log'
if(Test-Path $out){Remove-Item $out -Force}
if(Test-Path $err){Remove-Item $err -Force}
$proc = Start-Process -FilePath 'dotnet' -ArgumentList 'run','--project','src\Orchestrator.Api','-c','Release' -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
Write-Output "Started API PID: $($proc.Id)"
# Wait for API
$ready = $false
for ($i=0; $i -lt 30; $i++) {
    try {
        $r = Invoke-RestMethod -Uri 'http://localhost:5156/' -Method Get -TimeoutSec 2; Write-Output "HEALTH: $r"; $ready=$true; break
    } catch { Start-Sleep -Seconds 2 }
}
if(-not $ready){ Write-Output 'API not ready after wait'; Exit 2 }
# Submit task
$body = @{ AgentType='dummy'; Prompt='integration smoke from script'; WorkflowId = 'wf_integration' } | ConvertTo-Json
$resp = Invoke-RestMethod -Uri 'http://localhost:5156/tasks' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 10
$id = $resp.id
Write-Output "Submitted task id: $id"
# Poll for completion
$j=0; while($j -lt 120){ try { $t = Invoke-RestMethod -Uri "http://localhost:5156/tasks/$id" -Method Get -TimeoutSec 5; Write-Output "TASK: $($t | ConvertTo-Json -Depth 5)"; if ($t.state -ne 'Queued' -and $t.state -ne 'Running') { break } } catch { } Start-Sleep -Seconds 1; $j++ }
# Dump logs
if(Test-Path $out){ Get-Content $out -Tail 200 }
if(Test-Path $err){ Get-Content $err -Tail 200 }
# Teardown
Write-Output "Stopping API (PID: $($proc.Id))"
Stop-Process -Id $proc.Id -ErrorAction SilentlyContinue
Write-Output "Tearing down docker-compose services..."
docker-compose -f $compose down -v