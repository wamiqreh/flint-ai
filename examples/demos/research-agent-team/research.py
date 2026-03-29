#!/usr/bin/env python3
"""Research Agent Team — complex multi-agent DAG with human-in-the-loop.

Demonstrates:
  - Parallel execution (researcher-1 ∥ researcher-2)
  - Human approval gates (researcher-2 requires approval)
  - Multi-stage synthesis (analyst → writer)

Topology:
  planner → [researcher-1, researcher-2🔒] → analyst → writer

Usage:
    python research.py
"""

import sys
import time

from flint_ai import OrchestratorClient, Workflow, Node

FLINT_URL = "http://localhost:5156"

RESEARCH_TOPIC = (
    "The impact of AI agent orchestration on enterprise software development "
    "productivity in 2025"
)


def build_workflow() -> Workflow:
    """Construct the research team workflow."""
    wf = (
        Workflow("research-agent-team")
        # Stage 1: Plan the research
        .add(
            Node(
                "planner",
                agent="dummy",
                prompt=(
                    f"You are a research director. Create a detailed research "
                    f"plan for the following topic:\n\n"
                    f"  {RESEARCH_TOPIC}\n\n"
                    f"Output:\n"
                    f"1. Three specific research questions\n"
                    f"2. Methodology for each question\n"
                    f"3. Expected data sources"
                ),
            )
        )
        # Stage 2a: Researcher 1 — market trends (no approval needed)
        .add(
            Node(
                "researcher-1",
                agent="dummy",
                prompt=(
                    "You are a market research analyst. Based on the research "
                    "plan, investigate:\n"
                    "- Current adoption rates of AI orchestration platforms\n"
                    "- Market size and growth projections\n"
                    "- Key players and competitive landscape\n"
                    "Provide data points with sources."
                ),
            )
            .depends_on("planner")
            .with_retries(2)
        )
        # Stage 2b: Researcher 2 — technical analysis (requires approval)
        .add(
            Node(
                "researcher-2",
                agent="dummy",
                prompt=(
                    "You are a technical researcher. Based on the research "
                    "plan, investigate:\n"
                    "- Architectural patterns in agent orchestration\n"
                    "- Performance benchmarks (latency, throughput)\n"
                    "- Integration patterns with existing CI/CD pipelines\n"
                    "Provide concrete technical examples."
                ),
            )
            .depends_on("planner")
            .requires_approval()         # 🔒 Human must approve before this runs
            .with_retries(2)
        )
        # Stage 3: Analyst — synthesize findings
        .add(
            Node(
                "analyst",
                agent="dummy",
                prompt=(
                    "You are a senior analyst. Synthesize the findings from "
                    "both researchers into:\n"
                    "1. Three key insights\n"
                    "2. Identified gaps in the data\n"
                    "3. Actionable recommendations\n"
                    "Cross-reference market data with technical capabilities."
                ),
            )
            .depends_on("researcher-1", "researcher-2")
        )
        # Stage 4: Writer — produce final report
        .add(
            Node(
                "writer",
                agent="dummy",
                prompt=(
                    "You are a technical writer. Produce a polished research "
                    "report with:\n"
                    "- Executive summary (3 sentences)\n"
                    "- Key findings (bullet points)\n"
                    "- Analysis and recommendations\n"
                    "- Conclusion\n"
                    "Write in a clear, professional tone suitable for "
                    "C-level executives."
                ),
            )
            .depends_on("analyst")
        )
    )
    return wf


def main() -> None:
    print("=" * 60)
    print("  Flint Demo: Research Agent Team")
    print("=" * 60)
    print(f"\n📋 Topic: {RESEARCH_TOPIC}\n")

    client = OrchestratorClient(FLINT_URL)

    # --- Build & submit -------------------------------------------------------
    wf = build_workflow()
    definition = wf.build()

    # Show the DAG structure
    print("📐 Workflow DAG:")
    print(f"   Nodes: {[n.id for n in definition.nodes]}")
    for edge in definition.edges:
        print(f"   {edge.from_node_id:15s} ──▶ {edge.to_node_id}")
    approval_nodes = [n.id for n in definition.nodes if n.human_approval]
    if approval_nodes:
        print(f"   🔒 Approval required: {approval_nodes}")

    print("\n⬆️  Submitting workflow to Flint …")
    created = client.create_workflow(definition)
    print(f"   Created workflow: {created.id}")

    # --- Start execution ------------------------------------------------------
    print("▶️  Starting workflow …\n")
    start = time.time()
    client.start_workflow(created.id)

    # --- Poll nodes for completion --------------------------------------------
    nodes = client.get_workflow_nodes(created.id)
    task_ids = {n["Id"]: n.get("TaskId") for n in nodes if n.get("TaskId")}

    # Execution order for display
    execution_order = ["planner", "researcher-1", "researcher-2", "analyst", "writer"]
    ordered_tasks = [
        (nid, task_ids[nid]) for nid in execution_order if nid in task_ids
    ]

    timeline: list[tuple[str, str, float]] = []

    for node_id, task_id in ordered_tasks:
        node_start = time.time()
        label = f"{'🔒 ' if node_id == 'researcher-2' else '   '}{node_id}"

        # For the approval node, note the gate
        if node_id == "researcher-2":
            print(f"   ⏸️  {node_id} is waiting for human approval …")
            print(f"      (In production, approve via the UI or API)")
            print(f"      Auto-continuing for demo purposes.\n")

        result = client.wait_for_task(task_id, poll_interval_seconds=0.5)
        elapsed = time.time() - node_start

        status = "✅" if result.state == "Succeeded" else "❌"
        timeline.append((node_id, result.state, elapsed))
        print(f"   {status} {node_id:15s}  ({elapsed:.1f}s) → {result.state}")
        if result.result:
            preview = result.result[:100].replace("\n", " ")
            print(f"      └─ {preview}…")

    total = time.time() - start

    # --- Execution Timeline ---------------------------------------------------
    print("\n" + "-" * 60)
    print("  📊 Execution Timeline")
    print("-" * 60)
    max_bar = 30
    max_time = max(t for _, _, t in timeline) if timeline else 1
    for node_id, state, elapsed in timeline:
        bar_len = int((elapsed / max_time) * max_bar) if max_time > 0 else 1
        bar = "█" * max(bar_len, 1)
        lock = " 🔒" if node_id == "researcher-2" else ""
        print(f"   {node_id:15s} {bar} {elapsed:.1f}s{lock}")

    # Show parallel vs sequential comparison
    r1_time = next((t for n, _, t in timeline if n == "researcher-1"), 0)
    r2_time = next((t for n, _, t in timeline if n == "researcher-2"), 0)
    print(f"\n   Parallel stage:  max({r1_time:.1f}s, {r2_time:.1f}s) = {max(r1_time, r2_time):.1f}s")
    print(f"   Sequential alt:  {r1_time:.1f}s + {r2_time:.1f}s = {r1_time + r2_time:.1f}s")

    print(f"\n   Total wall-clock: {total:.1f}s")
    print("\n" + "=" * 60)
    print("  Research report complete!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Error: {exc}", file=sys.stderr)
        sys.exit(1)
