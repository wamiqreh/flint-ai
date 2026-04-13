"""Sequential Pipeline — A → B → C with data passing.

Research findings flow into the summary, which flows into the review.

Requires: PostgreSQL + Redis running (docker compose up -d)
          OPENAI_API_KEY environment variable.

Usage:
    python 03_sequential_pipeline.py
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
    instructions="Write a 2-sentence summary from the research.")
reviewer = FlintOpenAIAgent(name="reviewer", model="gpt-4o-mini",
    instructions="Score 1-10. Return JSON: {\"score\": N, \"note\": \"...\"}.")

# ── Start engine ──────────────────────────────────────────────────────────
print("Starting engine...\n")
configure_engine(agents=[researcher, writer, reviewer])
print("Pipeline: Research → Write → Review\n")

results = (
    Workflow("sequential")
    .add(Node("research", agent=researcher, prompt="Benefits of AI orchestration"))
    .add(Node("write", agent=writer, prompt="{research}").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="{write}").depends_on("write"))
    .run()
)

for nid, out in results.items():
    print(f"  [{nid}] {out[:150]}")

shutdown_engine()
print("\nDone. Dashboard: http://localhost:5160/ui/")
