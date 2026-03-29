param(
    [string]$ApiUrl = "http://localhost:5000",
    [int]$Count = 20,
    [int]$PollTimeoutSeconds = 120
)

Write-Host "Load test: submitting $Count tasks to $ApiUrl"
$Ids = @()
for ($i = 0; $i -lt $Count; $i++) {
    $id = [guid]::NewGuid().ToString()
    $payload = @{ Id = $id; AgentType = "dummy"; Prompt = "Load test $i"; WorkflowId = $null }
    try {
        Invoke-RestMethod -Uri "$ApiUrl/tasks" -Method Post -Body ($payload | ConvertTo-Json -Depth 5) -ContentType 'application/json' -ErrorAction Stop | Out-Null
        $Ids += $id
    }
    catch {
        Write-Warning ("Failed to submit task {0}: {1}" -f $id, $_)
    }
}

Write-Host "Submitted $($Ids.Count) tasks. Polling for completion..."
$start = Get-Date
while ($true) {
    $done = 0
    foreach ($id in $Ids) {
        try {
            $resp = Invoke-RestMethod -Uri "$ApiUrl/tasks/$id" -Method Get -ErrorAction Stop
            $state = $resp.state
            if ($state -ne 'Queued' -and $state -ne 'Pending' -and $state -ne 'Running') {
                $done++
            }
        }
        catch {
            # ignore
        }
    }
    Write-Host "Completed: $done / $($Ids.Count)"
    if ($done -eq $Ids.Count) { break }
    $elapsed = (New-TimeSpan -Start $start -End (Get-Date)).TotalSeconds
    if ($elapsed -gt $PollTimeoutSeconds) {
        Write-Warning "Timeout reached after $elapsed seconds"
        break
    }
    Start-Sleep -Seconds 1
}

Write-Host "Fetching final task states..."
foreach ($id in $Ids) {
    try {
        $resp = Invoke-RestMethod -Uri "$ApiUrl/tasks/$id" -Method Get -ErrorAction Stop
        Write-Host "$id -> $($resp.state)"
    }
    catch {
        Write-Host "$id -> error"
    }
}

Write-Host "Load test finished."