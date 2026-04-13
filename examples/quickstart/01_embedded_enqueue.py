"""Embedded Mode — Run & Enqueue (Global engine style).

Start the engine once, then enqueue multiple workflows from anywhere.
Engine stays running after workflows finish.

Requires: PostgreSQL + Redis running (docker compose up -d)
          OPENAI_API_KEY environment variable.

Usage:
    python 01_embedded_enqueue.py
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

# ── Start engine ONCE (stays running) ─────────────────────────────────────
print("Starting engine (Global engine mode)...\n")
configure_engine(agents=[writer])
print("Dashboard: http://localhost:5160/ui/")
print()

# ── Enqueue workflow 1 ────────────────────────────────────────────────────
r1 = (
    Workflow("task-1")
    .add(Node("s1", agent=writer, prompt="What is the capital of France?"))
    .run()
)
print(f"Task 1: {r1.get('s1', 'N/A')[:80]}...")

# ── Enqueue workflow 2 ────────────────────────────────────────────────────
r2 = (
    Workflow("task-2")
    .add(Node("s2", agent=writer, prompt="Explain Docker in one sentence"))
    .run()
)
print(f"Task 2: {r2.get('s2', 'N/A')[:80]}...")

# ── Enqueue workflow 3 ────────────────────────────────────────────────────
r3 = (
    Workflow("task-3")
    .add(Node("s3", agent=writer, prompt="What is Kubernetes in 10 words"))
    .run()
)
print(f"Task 3: {r3.get('s3', 'N/A')[:80]}...")

print("\nAll 3 workflows done. Engine still running.")
print("Verify: http://localhost:5160/ui/")
print("Press Enter to stop...")
input()
shutdown_engine()

