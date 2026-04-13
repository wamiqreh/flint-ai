"""Approval Gate — workflow pauses for human approval.

Draft runs, then waits for your approval before review continues.

Requires: PostgreSQL + Redis running (docker compose up -d)
          OPENAI_API_KEY environment variable.

Usage:
    python 05_approval_gate.py
"""

import os
import sys

os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
if not os.environ["OPENAI_API_KEY"].startswith("sk-"):
    print("Set OPENAI_API_KEY first.")
    sys.exit(1)

from flint_ai import Node, Workflow, configure_engine, shutdown_engine
from flint_ai.adapters.openai import FlintOpenAIAgent

writer = FlintOpenAIAgent(name="writer", model="gpt-4o-mini",
    instructions="Write a 2-sentence response.")
reviewer = FlintOpenAIAgent(name="reviewer", model="gpt-4o-mini",
    instructions="Score 1-10. Return JSON: {\"score\": N}.")

def on_approval(node_id: str, upstream: str) -> bool:
    print(f"\n  >>> APPROVAL: '{node_id}'")
    print(f"  Upstream: {upstream[:120]}...")
    return input("  Approve? (y/n): ").strip().lower() == "y"

# ── Start engine ──────────────────────────────────────────────────────────
print("Starting engine...\n")
configure_engine(agents=[writer, reviewer])
print("Pipeline: Draft → APPROVE → Review\n")

results = (
    Workflow("approval-test")
    .add(Node("draft", agent=writer, prompt="Write a tweet about AI in 2025"))
    .add(Node("review", agent=reviewer, prompt="{draft}").depends_on("draft").requires_approval())
    .run(on_approval=on_approval)
)

print()
for nid, out in results.items():
    if out:
        print(f"  [{nid}] {out[:120]}")
    else:
        print(f"  [{nid}] (success)")

shutdown_engine()
print("\nDone. Dashboard: http://localhost:5160/ui/")
