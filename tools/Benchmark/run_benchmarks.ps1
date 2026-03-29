<#
.SYNOPSIS
    Runs the full benchmark suite against the orchestrator.

.DESCRIPTION
    1. Starts the orchestrator via docker-compose.dev.yml
    2. Waits for the /health endpoint to respond
    3. Runs benchmarks at increasing scales (100, 500, 1000, 5000 tasks)
    4. Generates a Markdown comparison report
    5. Stops the orchestrator

.EXAMPLE
    .\run_benchmarks.ps1
    .\run_benchmarks.ps1 -Url http://localhost:5156 -SkipDockerStart
#>

param(
    [string]$Url = "http://localhost:5156",
    [string]$Agent = "dummy",
    [int]$HealthTimeout = 120,
    [switch]$SkipDockerStart,
    [switch]$SkipDockerStop
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Resolve-Path "$ScriptDir\..\.."
$ResultsDir = Join-Path $ScriptDir "results"

# Ensure results directory exists
New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null

# -- 1. Start the orchestrator -----------------------------------------------
if (-not $SkipDockerStart) {
    Write-Host "`n=== Starting orchestrator (docker-compose.dev.yml) ===" -ForegroundColor Cyan
    Push-Location $RepoRoot
    docker compose -f docker-compose.dev.yml up -d --build
    Pop-Location
}

# -- 2. Wait for health check ------------------------------------------------
Write-Host "`n=== Waiting for health check at $Url/health ===" -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds($HealthTimeout)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri "$Url/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($resp.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        # Not ready yet
    }
    Start-Sleep -Seconds 2
    Write-Host "  ... waiting" -ForegroundColor DarkGray
}
if (-not $healthy) {
    Write-Error "Orchestrator did not become healthy within $HealthTimeout seconds."
    exit 1
}
Write-Host "  Orchestrator is healthy!" -ForegroundColor Green

# -- 3. Install Python dependencies ------------------------------------------
Write-Host "`n=== Installing Python dependencies ===" -ForegroundColor Cyan
pip install -q -r "$ScriptDir\requirements.txt"

# -- 4. Run benchmarks at multiple scales ------------------------------------

$benchmarks = @(
    @{ Tasks = 100;  Concurrency = 5  },
    @{ Tasks = 500;  Concurrency = 10 },
    @{ Tasks = 1000; Concurrency = 20 },
    @{ Tasks = 5000; Concurrency = 50 }
)

foreach ($b in $benchmarks) {
    $tasks = $b.Tasks
    $conc  = $b.Concurrency
    Write-Host "`n=== Benchmark: $tasks tasks, concurrency $conc ===" -ForegroundColor Yellow

    $outputFile = Join-Path $ResultsDir "benchmark_${tasks}_${conc}.json"

    python "$ScriptDir\benchmark.py" `
        --url $Url `
        --tasks $tasks `
        --concurrency $conc `
        --agent $Agent `
        --warmup 5 `
        --output $outputFile

    if ($LASTEXITCODE -gt 1) {
        Write-Warning "Benchmark run ($tasks tasks) returned exit code $LASTEXITCODE"
    }

    # Brief pause between runs to let the server stabilise
    Start-Sleep -Seconds 3
}

# -- 5. Generate the comparison report ----------------------------------------
Write-Host "`n=== Generating report ===" -ForegroundColor Cyan
python "$ScriptDir\benchmark_report.py" --output "$ResultsDir\report.md"
Write-Host "  Report: $ResultsDir\report.md" -ForegroundColor Green

# -- 6. Stop the orchestrator -------------------------------------------------
if (-not $SkipDockerStop) {
    Write-Host "`n=== Stopping orchestrator ===" -ForegroundColor Cyan
    Push-Location $RepoRoot
    docker compose -f docker-compose.dev.yml down
    Pop-Location
}

Write-Host "`n=== Benchmarks complete ===" -ForegroundColor Green
Write-Host "Results directory: $ResultsDir"
Write-Host "Report:           $ResultsDir\report.md"
