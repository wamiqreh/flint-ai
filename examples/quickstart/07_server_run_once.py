"""Server Mode — Run in One Go.

Connects to running server, starts a worker, runs the workflow, stops worker.
API keys never leave your machine.

Requires:
  1. Server running: docker compose up -d  (or python -m flint_ai.server)
  2. OPENAI_API_KEY environment variable

Usage:
    python 07_server_run_once.py
"""

import os
import sys
import asyncio

os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
if not os.environ["OPENAI_API_KEY"].startswith("sk-"):
    print("Set OPENAI_API_KEY first.")
    sys.exit(1)

SERVER_URL = os.environ.get("FLINT_SERVER_URL", "http://localhost:5156")

from flint_ai import Node, Workflow
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.worker import FlintWorker

writer = FlintOpenAIAgent(name="writer", model="gpt-4o-mini",
    instructions="Give a 1-sentence response.")

async def main():
    # ── Start worker ──────────────────────────────────────────────────────
    print(f"Connecting to server at {SERVER_URL}...")
    worker = FlintWorker(server_url=SERVER_URL)
    worker.register("writer", writer)
    await worker.start_async(poll_interval=0.5, concurrency=5)
    print("Worker started.\n")

    try:
        # ── Run workflow ──────────────────────────────────────────────
        results = (
            Workflow("server-quick")
            .add(Node("s1", agent=writer, prompt="What is AI orchestration?"))
            .run(server_url=SERVER_URL)
        )

        for nid, out in results.items():
            print(f"  [{nid}] {out[:120]}")

    finally:
        worker.stop()
        print("\nDone. Server dashboard: http://localhost:5160/ui/")

asyncio.run(main())
