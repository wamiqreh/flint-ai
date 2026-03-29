# Smoke test script: start API (in-memory), submit one task, print status, then exit
$env:USE_INMEMORY_QUEUE='true'
$out='api_run_out.log'
$err='api_run_err.log'
if(Test-Path $out){Remove-Item $out -Force}
if(Test-Path $err){Remove-Item $err -Force}
$proc=Start-Process -FilePath 'dotnet' -ArgumentList 'run','--project','src\Orchestrator.Api','-c','Release' -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
Write-Output "Started API PID: $($proc.Id)"
$max=30; $i=0; $ready=$false
while($i -lt $max){ try{ $r=Invoke-RestMethod -Uri 'http://localhost:5156/' -Method Get -TimeoutSec 2; Write-Output "HEALTH: $r"; $ready=$true; break } catch { Start-Sleep -Seconds 1; $i++ } }
if(-not $ready){ Write-Output 'API not ready after wait'; Exit 2 }
$body = @{ AgentType='dummy'; Prompt='smoke test from script'; WorkflowId = 'wf_demo' } | ConvertTo-Json
$resp = Invoke-RestMethod -Uri 'http://localhost:5156/tasks' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 10
$id = $resp.id
Write-Output "Submitted task id: $id"
$j=0; while($j -lt 30){ try { $t = Invoke-RestMethod -Uri "http://localhost:5156/tasks/$id" -Method Get -TimeoutSec 5; Write-Output "TASK: $($t | ConvertTo-Json -Depth 5)"; if ($t.state -ne 'Queued') { break } } catch { } Start-Sleep -Seconds 1; $j++ }
# dump logs
if(Test-Path $out){ Get-Content $out -Tail 200 }
if(Test-Path $err){ Get-Content $err -Tail 200 }
