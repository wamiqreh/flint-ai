#!/usr/bin/env python3
"""Benchmark suite for Flint.

Submits tasks concurrently, polls until completion, and reports latency /
throughput / error-rate metrics with percentile breakdowns.

Usage:
    python benchmark.py --url http://localhost:5156 --tasks 1000 --concurrency 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

import httpx
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TaskMetrics:
    """Timing data collected for a single task."""
    task_id: str
    submit_start: float  # monotonic
    submit_end: float
    completed_at: Optional[float] = None
    final_state: Optional[str] = None
    error: Optional[str] = None

    @property
    def submit_latency_ms(self) -> float:
        return (self.submit_end - self.submit_start) * 1000

    @property
    def e2e_latency_ms(self) -> Optional[float]:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.submit_start) * 1000

    @property
    def queue_wait_ms(self) -> Optional[float]:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.submit_end) * 1000


@dataclass
class BenchmarkResult:
    """Aggregated benchmark results."""
    total_tasks: int
    concurrency: int
    agent_type: str
    warmup_tasks: int

    wall_clock_seconds: float = 0.0
    throughput_submitted_per_sec: float = 0.0
    throughput_completed_per_sec: float = 0.0

    submit_latency_p50_ms: float = 0.0
    submit_latency_p95_ms: float = 0.0
    submit_latency_p99_ms: float = 0.0
    submit_latency_max_ms: float = 0.0

    e2e_latency_p50_ms: float = 0.0
    e2e_latency_p95_ms: float = 0.0
    e2e_latency_p99_ms: float = 0.0
    e2e_latency_max_ms: float = 0.0

    queue_wait_p50_ms: float = 0.0
    queue_wait_p95_ms: float = 0.0
    queue_wait_p99_ms: float = 0.0
    queue_wait_max_ms: float = 0.0

    succeeded: int = 0
    failed: int = 0
    timed_out: int = 0
    error_rate_pct: float = 0.0
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def percentile(data: List[float], pct: float) -> float:
    """Return the *pct*-th percentile of *data* (0-100 scale)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (pct / 100) * (len(sorted_data) - 1)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


# ---------------------------------------------------------------------------
# Core benchmark logic
# ---------------------------------------------------------------------------

async def submit_task(
    client: httpx.AsyncClient,
    agent_type: str,
    index: int,
) -> TaskMetrics:
    """Submit a single task and record timing."""
    payload = {"AgentType": agent_type, "Prompt": f"benchmark payload {index}"}
    start = time.monotonic()
    try:
        resp = await client.post("/tasks", json=payload)
        end = time.monotonic()
        resp.raise_for_status()
        task_id = resp.json()["id"]
        return TaskMetrics(task_id=task_id, submit_start=start, submit_end=end)
    except Exception as exc:
        end = time.monotonic()
        return TaskMetrics(
            task_id="",
            submit_start=start,
            submit_end=end,
            final_state="SubmitError",
            error=str(exc),
        )


async def poll_task(
    client: httpx.AsyncClient,
    metrics: TaskMetrics,
    poll_interval: float,
    timeout: float,
) -> None:
    """Poll until the task reaches a terminal state or times out."""
    if metrics.error:
        return
    terminal = {"Succeeded", "Failed", "DeadLetter"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = await client.get(f"/tasks/{metrics.task_id}")
            resp.raise_for_status()
            state = resp.json().get("state", "")
            if state in terminal:
                metrics.completed_at = time.monotonic()
                metrics.final_state = state
                return
        except Exception:
            pass
        await asyncio.sleep(poll_interval)
    metrics.final_state = "Timeout"
    metrics.completed_at = time.monotonic()


async def run_benchmark(
    url: str,
    total_tasks: int,
    concurrency: int,
    agent_type: str,
    warmup_count: int,
    poll_interval: float,
    task_timeout: float,
    console: Console,
) -> BenchmarkResult:
    """Execute the full benchmark and return aggregated results."""

    limits = httpx.Limits(
        max_connections=concurrency + 20,
        max_keepalive_connections=concurrency + 10,
    )
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0)

    async with httpx.AsyncClient(
        base_url=url.rstrip("/"), limits=limits, timeout=timeout,
    ) as client:
        # -- Warmup ----------------------------------------------------------
        if warmup_count > 0:
            console.print(f"[dim]Running {warmup_count} warmup tasks...[/dim]")
            warmup_sem = asyncio.Semaphore(concurrency)

            async def _warmup(i: int) -> None:
                async with warmup_sem:
                    m = await submit_task(client, agent_type, i)
                    if not m.error:
                        await poll_task(client, m, poll_interval, task_timeout)

            await asyncio.gather(*[_warmup(i) for i in range(warmup_count)])
            console.print("[dim]Warmup complete.[/dim]\n")

        # -- Submit phase ----------------------------------------------------
        console.print(
            f"Submitting [bold]{total_tasks}[/bold] tasks "
            f"with concurrency [bold]{concurrency}[/bold]..."
        )
        sem = asyncio.Semaphore(concurrency)
        all_metrics: List[TaskMetrics] = []
        wall_start = time.monotonic()

        async def _submit(i: int) -> TaskMetrics:
            async with sem:
                return await submit_task(client, agent_type, i)

        all_metrics = await asyncio.gather(
            *[_submit(i) for i in range(total_tasks)]
        )
        submit_wall = time.monotonic() - wall_start
        console.print(
            f"[green]All {total_tasks} tasks submitted in "
            f"{submit_wall:.2f}s[/green]"
        )

        # -- Poll phase ------------------------------------------------------
        console.print("Polling for completion...")
        pending = [m for m in all_metrics if not m.error]
        poll_sem = asyncio.Semaphore(concurrency)

        async def _poll(m: TaskMetrics) -> None:
            async with poll_sem:
                await poll_task(client, m, poll_interval, task_timeout)

        await asyncio.gather(*[_poll(m) for m in pending])
        wall_end = time.monotonic()
        wall_clock = wall_end - wall_start
        console.print(f"[green]All tasks resolved in {wall_clock:.2f}s[/green]\n")

    # -- Aggregate -----------------------------------------------------------
    result = BenchmarkResult(
        total_tasks=total_tasks,
        concurrency=concurrency,
        agent_type=agent_type,
        warmup_tasks=warmup_count,
        wall_clock_seconds=round(wall_clock, 3),
    )

    submit_latencies = [m.submit_latency_ms for m in all_metrics if not m.error]
    e2e_latencies = [
        m.e2e_latency_ms for m in all_metrics if m.e2e_latency_ms is not None
    ]
    queue_waits = [
        m.queue_wait_ms for m in all_metrics if m.queue_wait_ms is not None
    ]

    if submit_latencies:
        result.submit_latency_p50_ms = round(percentile(submit_latencies, 50), 2)
        result.submit_latency_p95_ms = round(percentile(submit_latencies, 95), 2)
        result.submit_latency_p99_ms = round(percentile(submit_latencies, 99), 2)
        result.submit_latency_max_ms = round(max(submit_latencies), 2)

    if e2e_latencies:
        result.e2e_latency_p50_ms = round(percentile(e2e_latencies, 50), 2)
        result.e2e_latency_p95_ms = round(percentile(e2e_latencies, 95), 2)
        result.e2e_latency_p99_ms = round(percentile(e2e_latencies, 99), 2)
        result.e2e_latency_max_ms = round(max(e2e_latencies), 2)

    if queue_waits:
        result.queue_wait_p50_ms = round(percentile(queue_waits, 50), 2)
        result.queue_wait_p95_ms = round(percentile(queue_waits, 95), 2)
        result.queue_wait_p99_ms = round(percentile(queue_waits, 99), 2)
        result.queue_wait_max_ms = round(max(queue_waits), 2)

    result.succeeded = sum(1 for m in all_metrics if m.final_state == "Succeeded")
    result.failed = sum(
        1 for m in all_metrics if m.final_state in {"Failed", "DeadLetter", "SubmitError"}
    )
    result.timed_out = sum(1 for m in all_metrics if m.final_state == "Timeout")
    error_count = result.failed + result.timed_out
    result.error_rate_pct = round(error_count / total_tasks * 100, 2)
    result.errors = [
        f"{m.task_id or 'N/A'}: {m.error or m.final_state}"
        for m in all_metrics
        if m.final_state not in {"Succeeded", None}
    ][:20]  # cap error list

    if wall_clock > 0:
        result.throughput_submitted_per_sec = round(total_tasks / submit_wall, 2)
        result.throughput_completed_per_sec = round(result.succeeded / wall_clock, 2)

    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_results(result: BenchmarkResult, console: Console) -> None:
    """Render benchmark results as rich tables."""
    # -- Summary table -------------------------------------------------------
    summary = Table(title="Benchmark Summary", show_header=False, min_width=50)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Total tasks", str(result.total_tasks))
    summary.add_row("Concurrency", str(result.concurrency))
    summary.add_row("Agent type", result.agent_type)
    summary.add_row("Warmup tasks", str(result.warmup_tasks))
    summary.add_row("Wall-clock time", f"{result.wall_clock_seconds:.2f} s")
    summary.add_row("Submit throughput", f"{result.throughput_submitted_per_sec:.1f} tasks/s")
    summary.add_row("Completion throughput", f"{result.throughput_completed_per_sec:.1f} tasks/s")
    summary.add_row("Succeeded", str(result.succeeded))
    summary.add_row("Failed", str(result.failed))
    summary.add_row("Timed out", str(result.timed_out))
    summary.add_row(
        "Error rate",
        f"[red]{result.error_rate_pct}%[/red]"
        if result.error_rate_pct > 0
        else f"[green]{result.error_rate_pct}%[/green]",
    )
    console.print(summary)
    console.print()

    # -- Latency table -------------------------------------------------------
    latency = Table(title="Latency Breakdown (ms)")
    latency.add_column("Metric", style="bold")
    latency.add_column("p50", justify="right")
    latency.add_column("p95", justify="right")
    latency.add_column("p99", justify="right")
    latency.add_column("max", justify="right")
    latency.add_row(
        "Submit (POST /tasks)",
        f"{result.submit_latency_p50_ms:.1f}",
        f"{result.submit_latency_p95_ms:.1f}",
        f"{result.submit_latency_p99_ms:.1f}",
        f"{result.submit_latency_max_ms:.1f}",
    )
    latency.add_row(
        "End-to-end",
        f"{result.e2e_latency_p50_ms:.1f}",
        f"{result.e2e_latency_p95_ms:.1f}",
        f"{result.e2e_latency_p99_ms:.1f}",
        f"{result.e2e_latency_max_ms:.1f}",
    )
    latency.add_row(
        "Queue wait",
        f"{result.queue_wait_p50_ms:.1f}",
        f"{result.queue_wait_p95_ms:.1f}",
        f"{result.queue_wait_p99_ms:.1f}",
        f"{result.queue_wait_max_ms:.1f}",
    )
    console.print(latency)

    if result.errors:
        console.print(f"\n[red]Sample errors ({len(result.errors)}):[/red]")
        for err in result.errors[:5]:
            console.print(f"  • {err}")


def save_results(result: BenchmarkResult, output_path: Path) -> None:
    """Write benchmark results to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark the Flint",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:5156",
        help="Base URL of the orchestrator API (default: %(default)s)",
    )
    parser.add_argument(
        "--tasks",
        type=int,
        default=100,
        help="Number of tasks to submit (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of parallel submitters (default: %(default)s)",
    )
    parser.add_argument(
        "--agent",
        default="dummy",
        help="Agent type to benchmark (default: %(default)s)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="Number of warmup tasks (default: %(default)s)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.25,
        help="Seconds between poll requests (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-task timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSON output path (default: results/benchmark_<tasks>_<concurrency>.json)",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    console = Console()

    console.rule("[bold blue]Flint — Benchmark[/bold blue]")
    console.print(
        f"Target: [bold]{args.url}[/bold]  |  "
        f"Tasks: [bold]{args.tasks}[/bold]  |  "
        f"Concurrency: [bold]{args.concurrency}[/bold]  |  "
        f"Agent: [bold]{args.agent}[/bold]"
    )
    console.print()

    result = await run_benchmark(
        url=args.url,
        total_tasks=args.tasks,
        concurrency=args.concurrency,
        agent_type=args.agent,
        warmup_count=args.warmup,
        poll_interval=args.poll_interval,
        task_timeout=args.timeout,
        console=console,
    )

    console.print()
    print_results(result, console)

    output_path = Path(
        args.output
        or str(
            Path(__file__).parent
            / "results"
            / f"benchmark_{args.tasks}_{args.concurrency}.json"
        )
    )
    save_results(result, output_path)
    console.print(f"\n[dim]Results saved to {output_path}[/dim]")

    sys.exit(1 if result.error_rate_pct > 10 else 0)


if __name__ == "__main__":
    asyncio.run(main())
