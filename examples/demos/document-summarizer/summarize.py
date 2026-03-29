#!/usr/bin/env python3
"""Document Summarizer — fan-out / fan-in parallel workflow.

Demonstrates Flint's map-reduce pattern:
  split → [chunk-1, chunk-2, chunk-3] → merge

Usage:
    python summarize.py
"""

import sys
import time

from flint_ai import OrchestratorClient, Workflow, Node

FLINT_URL = "http://localhost:5156"

# Sample document to summarize (three logical sections)
SAMPLE_DOCUMENT = """
SECTION 1 — INTRODUCTION
Artificial intelligence has transformed software development over the past
decade. From code completion to automated testing, AI-powered tools are now
integral to the modern developer workflow. This report examines the current
state of AI in software engineering and forecasts emerging trends.

SECTION 2 — CURRENT LANDSCAPE
Large language models (LLMs) such as GPT-4 and Claude power a new generation
of coding assistants. These tools can generate code, explain complex systems,
write documentation, and even perform code reviews. Adoption has grown 300%
year-over-year, with over 70% of Fortune 500 companies integrating AI into
their CI/CD pipelines.

SECTION 3 — FUTURE OUTLOOK
The next frontier is autonomous agent orchestration — systems where multiple
AI agents collaborate on complex tasks. Frameworks like Flint enable
developers to build DAG-based workflows where specialized agents handle
different stages of a pipeline, with built-in retry logic, human-in-the-loop
gates, and real-time observability.
"""


def build_workflow() -> Workflow:
    """Construct the fan-out / fan-in summarization workflow."""
    wf = (
        Workflow("document-summarizer")
        # Entry point: split the document
        .add(
            Node(
                "split",
                agent="dummy",
                prompt=(
                    "You are a document processor. Split the following document "
                    "into 3 logical sections and output each section as-is:\n\n"
                    f"{SAMPLE_DOCUMENT}"
                ),
            )
        )
        # Parallel chunk summarizers (fan-out)
        .add(
            Node(
                "chunk-1",
                agent="dummy",
                prompt=(
                    "Summarize SECTION 1 (Introduction) in 2-3 sentences. "
                    "Focus on the main thesis and scope."
                ),
            ).depends_on("split")
        )
        .add(
            Node(
                "chunk-2",
                agent="dummy",
                prompt=(
                    "Summarize SECTION 2 (Current Landscape) in 2-3 sentences. "
                    "Include key statistics and examples."
                ),
            ).depends_on("split")
        )
        .add(
            Node(
                "chunk-3",
                agent="dummy",
                prompt=(
                    "Summarize SECTION 3 (Future Outlook) in 2-3 sentences. "
                    "Highlight the most important predictions."
                ),
            ).depends_on("split")
        )
        # Merge all summaries (fan-in)
        .add(
            Node(
                "merge",
                agent="dummy",
                prompt=(
                    "Combine the three section summaries into a single coherent "
                    "executive summary (5-7 sentences). Ensure smooth transitions "
                    "between sections and end with a key takeaway."
                ),
            ).depends_on("chunk-1", "chunk-2", "chunk-3")
        )
    )
    return wf


def main() -> None:
    print("=" * 60)
    print("  Flint Demo: Document Summarizer (Fan-Out / Fan-In)")
    print("=" * 60)

    client = OrchestratorClient(FLINT_URL)

    # --- Build & submit -------------------------------------------------------
    wf = build_workflow()
    definition = wf.build()

    print(f"\n📐 Workflow: {definition.id}")
    print(f"   Nodes:    {[n.id for n in definition.nodes]}")
    print(f"   Edges:    {[(e.from_node_id, e.to_node_id) for e in definition.edges]}")

    print("\n⬆️  Submitting workflow to Flint …")
    created = client.create_workflow(definition)
    print(f"   Created workflow: {created.id}")

    # --- Start execution ------------------------------------------------------
    print("▶️  Starting workflow …")
    start = time.time()
    client.start_workflow(created.id)

    # --- Poll nodes for completion --------------------------------------------
    nodes = client.get_workflow_nodes(created.id)
    task_ids = {n["Id"]: n.get("TaskId") for n in nodes if n.get("TaskId")}

    print(f"\n⏳ Waiting for {len(task_ids)} tasks …\n")

    # Track parallel execution timing
    node_timings: dict[str, float] = {}

    for node_id, task_id in task_ids.items():
        node_start = time.time()
        result = client.wait_for_task(task_id, poll_interval_seconds=0.5)
        elapsed = time.time() - node_start

        node_timings[node_id] = elapsed
        status = "✅" if result.state == "Succeeded" else "❌"
        print(f"   {status} {node_id:10s}  ({elapsed:.1f}s) → {result.state}")
        if result.result:
            preview = result.result[:120].replace("\n", " ")
            print(f"      └─ {preview}…")

    total = time.time() - start

    # --- Summary --------------------------------------------------------------
    parallel_nodes = ["chunk-1", "chunk-2", "chunk-3"]
    parallel_total = sum(node_timings.get(n, 0) for n in parallel_nodes)
    parallel_max = max((node_timings.get(n, 0) for n in parallel_nodes), default=0)

    print("\n" + "-" * 60)
    print("  ⏱️  Timing Summary")
    print(f"     Total wall-clock:         {total:.1f}s")
    print(f"     Parallel chunks (sum):    {parallel_total:.1f}s")
    print(f"     Parallel chunks (max):    {parallel_max:.1f}s")
    if parallel_total > 0:
        speedup = parallel_total / max(parallel_max, 0.01)
        print(f"     Parallel speedup:         {speedup:.1f}×")
    print("=" * 60)
    print("  Summarization complete!")
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
