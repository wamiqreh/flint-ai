# Benchmark Suite

Performance benchmarks for the Flint. Measures throughput, latency percentiles, queue wait times, and error rates at varying scales.

## Quick Start

```bash
# From the repository root
cd tools/Benchmark

# Install dependencies
pip install -r requirements.txt

# Run a single benchmark (assumes orchestrator is running on localhost:5156)
python benchmark.py --url http://localhost:5156 --tasks 100 --concurrency 10
```

## Full Automated Suite

The PowerShell script handles everything — starts Docker, runs benchmarks at multiple scales, generates a report, and stops Docker:

```powershell
.\run_benchmarks.ps1
```

Options:
- `-Url <string>` — Override the orchestrator URL (default: `http://localhost:5156`)
- `-Agent <string>` — Agent type to benchmark (default: `dummy`)
- `-HealthTimeout <int>` — Seconds to wait for health check (default: `120`)
- `-SkipDockerStart` — Skip starting Docker (use if orchestrator is already running)
- `-SkipDockerStop` — Skip stopping Docker after benchmarks

```powershell
# Run against an already-running instance
.\run_benchmarks.ps1 -SkipDockerStart -SkipDockerStop
```

## benchmark.py

The core benchmark script. Submits tasks concurrently, polls until completion, and prints a rich results table.

### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--url` | `http://localhost:5156` | Orchestrator base URL |
| `--tasks` | `100` | Number of tasks to submit |
| `--concurrency` | `10` | Parallel submitters |
| `--agent` | `dummy` | Agent type |
| `--warmup` | `5` | Warmup tasks (metrics discarded) |
| `--poll-interval` | `0.25` | Seconds between status polls |
| `--timeout` | `120` | Per-task timeout in seconds |
| `--output` | `results/benchmark_<N>_<C>.json` | JSON output path |

### Metrics Collected

| Metric | Description |
|---|---|
| **Submit throughput** | Tasks submitted per second |
| **Completion throughput** | Tasks completed per second (wall clock) |
| **Submit latency** | Duration of the `POST /tasks` call (p50, p95, p99, max) |
| **End-to-end latency** | Time from submit to terminal state (p50, p95, p99, max) |
| **Queue wait time** | Time from submit-response to completion (p50, p95, p99, max) |
| **Error rate** | Percentage of failed + timed-out tasks |

### Example

```bash
python benchmark.py --url http://localhost:5156 --tasks 1000 --concurrency 20

# Output:
# ─── Flint — Benchmark ───
# Target: http://localhost:5156  |  Tasks: 1000  |  Concurrency: 20  |  Agent: dummy
#
# Submitting 1000 tasks with concurrency 20...
# All 1000 tasks submitted in 2.34s
# Polling for completion...
# All tasks resolved in 18.42s
#
# ┌───────────────────────────┐
# │    Benchmark Summary      │
# ├───────────────┬───────────┤
# │ Total tasks   │      1000 │
# │ ...           │       ... │
# └───────────────┴───────────┘
```

## benchmark_report.py

Generates a Markdown comparison report from JSON result files.

```bash
# Generate from all results in results/
python benchmark_report.py

# Or specify files explicitly
python benchmark_report.py results/benchmark_100_5.json results/benchmark_1000_20.json

# Custom output path
python benchmark_report.py --output my_report.md
```

Output goes to `results/report.md` by default.

## Results Directory

```
results/
├── benchmark_100_5.json       # Raw results per run
├── benchmark_500_10.json
├── benchmark_1000_20.json
├── benchmark_5000_50.json
└── report.md                  # Comparison report
```

The `results/` directory is gitignored — results are machine-specific and should not be committed.

## Tips

- **Baseline first**: Run with low task counts to establish a baseline before stress testing.
- **DummyAgent latency**: The `dummy` agent has a built-in 50–300ms random delay, so end-to-end latency will always include that.
- **In-memory vs Redis**: Run benchmarks against both `docker-compose.dev.yml` (in-memory) and `docker-compose.yml` (Redis) to compare queue backend performance.
- **Concurrency tuning**: Increase `--concurrency` to find the server's saturation point.
