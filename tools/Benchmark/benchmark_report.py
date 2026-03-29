#!/usr/bin/env python3
"""Generate a Markdown report from benchmark JSON result files.

Usage:
    python benchmark_report.py                          # all JSONs in results/
    python benchmark_report.py results/bench_100_10.json results/bench_1000_20.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def load_results(paths: List[Path]) -> List[Dict[str, Any]]:
    """Load and return benchmark result dicts from JSON files."""
    results: List[Dict[str, Any]] = []
    for p in sorted(paths):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        data["_source_file"] = p.name
        results.append(data)
    return results


def build_report(results: List[Dict[str, Any]]) -> str:
    """Create a Markdown report string from benchmark results."""
    lines: List[str] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# Benchmark Report")
    lines.append("")
    lines.append(f"_Generated: {timestamp}_")
    lines.append("")

    # -- Summary table -------------------------------------------------------
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Run | Tasks | Concurrency | Agent | Wall Clock (s) "
        "| Submit tp (t/s) | Complete tp (t/s) | Error % |"
    )
    lines.append(
        "|-----|------:|------------:|-------|---------------:"
        "|----------------:|------------------:|--------:|"
    )
    for r in results:
        lines.append(
            f"| {r.get('_source_file', '-')} "
            f"| {r['total_tasks']} "
            f"| {r['concurrency']} "
            f"| {r['agent_type']} "
            f"| {r['wall_clock_seconds']:.2f} "
            f"| {r['throughput_submitted_per_sec']:.1f} "
            f"| {r['throughput_completed_per_sec']:.1f} "
            f"| {r['error_rate_pct']:.1f} |"
        )
    lines.append("")

    # -- Latency table -------------------------------------------------------
    lines.append("## Latency (ms)")
    lines.append("")
    lines.append(
        "| Run | Submit p50 | Submit p95 | Submit p99 "
        "| E2E p50 | E2E p95 | E2E p99 | E2E max "
        "| Queue p50 | Queue p95 |"
    )
    lines.append(
        "|-----|----------:|-----------:|-----------:"
        "|--------:|--------:|--------:|--------:"
        "|----------:|----------:|"
    )
    for r in results:
        lines.append(
            f"| {r.get('_source_file', '-')} "
            f"| {r['submit_latency_p50_ms']:.1f} "
            f"| {r['submit_latency_p95_ms']:.1f} "
            f"| {r['submit_latency_p99_ms']:.1f} "
            f"| {r['e2e_latency_p50_ms']:.1f} "
            f"| {r['e2e_latency_p95_ms']:.1f} "
            f"| {r['e2e_latency_p99_ms']:.1f} "
            f"| {r['e2e_latency_max_ms']:.1f} "
            f"| {r['queue_wait_p50_ms']:.1f} "
            f"| {r['queue_wait_p95_ms']:.1f} |"
        )
    lines.append("")

    # -- Outcome table -------------------------------------------------------
    lines.append("## Outcomes")
    lines.append("")
    lines.append("| Run | Succeeded | Failed | Timed Out | Error Rate |")
    lines.append("|-----|----------:|-------:|----------:|-----------:|")
    for r in results:
        lines.append(
            f"| {r.get('_source_file', '-')} "
            f"| {r['succeeded']} "
            f"| {r['failed']} "
            f"| {r['timed_out']} "
            f"| {r['error_rate_pct']:.1f}% |"
        )
    lines.append("")

    # -- Comparison placeholder ----------------------------------------------
    lines.append("## Configuration Comparison")
    lines.append("")
    lines.append(
        "To compare different configurations (e.g. in-memory vs Redis, "
        "different concurrency limits), run the benchmark with different "
        "settings and place the JSON files in the `results/` directory. "
        "Re-run this report generator to see them side by side."
    )
    lines.append("")
    lines.append("### Suggested comparisons")
    lines.append("")
    lines.append("| Configuration | Command |")
    lines.append("|---------------|---------|")
    lines.append(
        "| Baseline (in-memory, low load) | "
        "`python benchmark.py --tasks 100 --concurrency 5` |"
    )
    lines.append(
        "| High concurrency | "
        "`python benchmark.py --tasks 1000 --concurrency 50` |"
    )
    lines.append(
        "| Stress test | "
        "`python benchmark.py --tasks 5000 --concurrency 100` |"
    )
    lines.append(
        "| Redis queue backend | "
        "_(start with docker-compose.yml, then benchmark)_ |"
    )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown benchmark report from JSON result files.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="JSON result files (default: all *.json in results/)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output markdown path (default: results/report.md)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    results_dir = Path(__file__).parent / "results"
    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        paths = list(results_dir.glob("benchmark_*.json"))

    if not paths:
        print("No benchmark result files found. Run benchmark.py first.", file=sys.stderr)
        sys.exit(1)

    results = load_results(paths)
    report = build_report(results)

    output_path = Path(args.output or str(results_dir / "report.md"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"Report written to {output_path}")
    print(f"  ({len(results)} benchmark run(s) included)")


if __name__ == "__main__":
    main()
