#!/usr/bin/env python3
"""Code Review Pipeline — sequential 3-node workflow.

Demonstrates Flint's linear prompt-chaining pattern:
  generate → review → summarize

Usage:
    python workflow.py
"""

import sys
import time

from flint_ai import OrchestratorClient, Workflow, Node

FLINT_URL = "http://localhost:5156"


def build_workflow() -> Workflow:
    """Construct the code-review pipeline using the Flint DSL."""
    wf = (
        Workflow("code-review-pipeline")
        # Stage 1: Generate code from a spec
        .add(
            Node(
                "generate",
                agent="dummy",
                prompt=(
                    "Write a Python function called `merge_sorted_lists` that "
                    "takes two sorted lists and returns a single merged sorted "
                    "list. Include type hints and a docstring."
                ),
            )
        )
        # Stage 2: Review the generated code
        .add(
            Node(
                "review",
                agent="dummy",
                prompt=(
                    "You are a senior Python engineer. Review the code produced "
                    "by the previous step. Check for:\n"
                    "- Correctness and edge cases\n"
                    "- Performance (time/space complexity)\n"
                    "- Style and PEP 8 compliance\n"
                    "- Missing tests or documentation\n"
                    "Provide actionable feedback."
                ),
            ).depends_on("generate")
        )
        # Stage 3: Summarize code + review into a final report
        .add(
            Node(
                "summarize",
                agent="dummy",
                prompt=(
                    "Create a concise final report that includes:\n"
                    "1. The generated code\n"
                    "2. Key findings from the review\n"
                    "3. A quality score (1-10)\n"
                    "4. Recommended next steps"
                ),
            ).depends_on("review")
        )
    )
    return wf


def main() -> None:
    print("=" * 60)
    print("  Flint Demo: Code Review Pipeline")
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
    client.start_workflow(created.id)

    # --- Poll nodes for completion --------------------------------------------
    nodes = client.get_workflow_nodes(created.id)
    task_ids = {n["Id"]: n.get("TaskId") for n in nodes if n.get("TaskId")}

    print(f"\n⏳ Waiting for {len(task_ids)} tasks …\n")
    for node_id, task_id in task_ids.items():
        result = client.wait_for_task(task_id, poll_interval_seconds=0.5)
        status = "✅" if result.state == "Succeeded" else "❌"
        print(f"   {status} {node_id:12s} → {result.state}")
        if result.result:
            preview = result.result[:120].replace("\n", " ")
            print(f"      └─ {preview}…")

    # --- Done -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  Pipeline complete!")
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
