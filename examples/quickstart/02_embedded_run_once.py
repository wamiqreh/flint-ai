"""Embedded Mode — Run in One Go.

Engine starts, runs the workflow, stops. Simple, no boilerplate.

Requires: PostgreSQL + Redis running (docker compose up -d)
          OPENAI_API_KEY environment variable.

Usage:
    python 02_embedded_run_once.py
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
    instructions="Give a 1-sentence response.")

# ── Start engine, run, stop (all in workflow.run()) ───────────────────────
print("Running workflow (engine starts & stops automatically)...\n")
configure_engine(agents=[writer])

results = (
    Workflow("quick-task")
    .add(Node("s1", agent=writer, prompt="What is AI orchestration in 2025?"))
    .run()
)

for nid, out in results.items():
    print(f"  [{nid}] {out[:120]}")

shutdown_engine()
print("\nDone. Dashboard was at http://localhost:5160/ui/")
