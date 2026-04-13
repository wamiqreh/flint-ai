"""Server Mode — Connect to running server, enqueue from client.

Starts a FlintWorker that claims tasks from the server and executes locally.
API keys never leave your machine.

Requires:
  1. Server running: docker compose up -d  (or python -m flint_ai.server)
  2. OPENAI_API_KEY environment variable

Usage:
    python 06_server_enqueue.py
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

# ── Start worker (connects to server) ─────────────────────────────────────
print(f"Connecting to server at {SERVER_URL}...")
worker = FlintWorker(server_url=SERVER_URL)
worker.register("writer", writer)

async def main():
    await worker.start_async(poll_interval=1.0, concurrency=5)
    print("Worker running. Enqueueing workflows...\n")

    # ── Workflow 1 ────────────────────────────────────────────────────
    r1 = (
        Workflow("server-task-1")
        .add(Node("s1", agent=writer, prompt="What is the capital of France?"))
        .run(server_url=SERVER_URL)
    )
    print(f"Task 1: {r1.get('s1', 'N/A')[:80]}...")

    # ── Workflow 2 ────────────────────────────────────────────────────
    r2 = (
        Workflow("server-task-2")
        .add(Node("s2", agent=writer, prompt="Explain Docker in one sentence"))
        .run(server_url=SERVER_URL)
    )
    print(f"Task 2: {r2.get('s2', 'N/A')[:80]}...")

    print("\nAll workflows done. Worker still polling.")
    print("Press Enter to stop worker...")
    await asyncio.get_event_loop().run_in_executor(None, input)
    worker.stop()
    print("Done.")

asyncio.run(main())
