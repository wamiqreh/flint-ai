"""Fan-out / Fan-in — A → (B, C) → D.

Research feeds into both Translate and Summarize (parallel).
Both must complete before Combine runs.

Requires: PostgreSQL + Redis running (docker compose up -d)
          OPENAI_API_KEY environment variable.

Usage:
    python 04_fanout_fanin.py
"""

import os
import sys

os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
if not os.environ["OPENAI_API_KEY"].startswith("sk-"):
    print("Set OPENAI_API_KEY first.")
    sys.exit(1)

from flint_ai import Node, Workflow, configure_engine, shutdown_engine
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(name="researcher", model="gpt-4o-mini",
    instructions="Give 3 bullet points on the topic.")
writer = FlintOpenAIAgent(name="writer", model="gpt-4o-mini",
    instructions="Write a 1-sentence response.")
reviewer = FlintOpenAIAgent(name="reviewer", model="gpt-4o-mini",
    instructions="Combine the two inputs into a short summary.")

# ── Start engine ──────────────────────────────────────────────────────────
print("Starting engine...\n")
configure_engine(agents=[researcher, writer, reviewer])
print("Fan-out: Research → (Translate + Summarize) → Combine\n")

results = (
    Workflow("fanout")
    .add(Node("research", agent=researcher, prompt="Key AI trends 2025"))
    .add(Node("translate", agent=writer, prompt="Translate to French: {research}").depends_on("research"))
    .add(Node("summarize", agent=writer, prompt="Summarize in one sentence: {research}").depends_on("research"))
    .add(Node("combine", agent=reviewer, prompt="Combine:\n{translate}\n---\n{summarize}").depends_on("translate", "summarize"))
    .run()
)

for nid, out in results.items():
    print(f"  [{nid}] {out[:120]}")

shutdown_engine()
print("\nDone. Dashboard: http://localhost:5160/ui/")
