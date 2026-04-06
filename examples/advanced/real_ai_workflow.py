"""Real AI Agent Workflow — runs actual OpenAI calls through Flint's orchestrator.

Architecture:
  • The CLIENT always provides and executes the agents (your code, your API keys)
  • The SERVER only orchestrates: queuing, DAG scheduling, retries, DLQ, dashboard
  • In embedded mode, the engine wraps your adapters internally
  • In remote mode, a FlintWorker on your machine claims tasks and runs them locally

Demonstrates:
  1. Embedded mode  — Workflow.run() starts an in-process engine
  2. Remote mode    — Workflow.run(server_url=...) talks to a running server
  3. Standalone worker — FlintWorker polls a server independently
  4. Dashboard monitoring after execution

Usage:
  # Set your API key
  export OPENAI_API_KEY=sk-...

  # Option 1: Embedded mode (self-contained, no Docker needed)
  python examples/real_ai_workflow.py

  # Option 2: Against a running server (start server first)
  python examples/real_ai_workflow.py --server http://localhost:5156

  # Option 3: Standalone worker (registers agents, polls server)
  python examples/real_ai_workflow.py --worker http://localhost:5156
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import httpx

from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent


# ---------------------------------------------------------------------------
# 1) Define agents — these ALWAYS live on the CLIENT side
# ---------------------------------------------------------------------------
def create_agents() -> dict[str, FlintOpenAIAgent]:
    """Create the OpenAI agents. These run on YOUR machine, not the server."""
    return {
        "researcher": FlintOpenAIAgent(
            name="researcher",
            model="gpt-4o-mini",
            instructions=(
                "You are an expert technology researcher. "
                "Provide factual, well-structured findings with evidence. "
                "Be concise but thorough."
            ),
        ),
        "analyst": FlintOpenAIAgent(
            name="analyst",
            model="gpt-4o-mini",
            instructions=(
                "You are a strategic analyst. "
                "Evaluate findings critically, identify implications, "
                "and rate their likelihood on a scale of 1-10."
            ),
        ),
        "writer": FlintOpenAIAgent(
            name="writer",
            model="gpt-4o-mini",
            instructions=(
                "You are a concise technical writer. "
                "Write clear, executive-level summaries. Max 150 words."
            ),
        ),
    }


# ---------------------------------------------------------------------------
# 2) Build the workflow DAG — agents are attached to nodes
# ---------------------------------------------------------------------------
def build_research_pipeline(agents: dict[str, FlintOpenAIAgent]) -> Workflow:
    """Build a 3-step research pipeline DAG.

    research ──→ analyze ──→ summarize
       └──────────────────→ summarize
    """
    topic = "How autonomous AI agents will change software engineering by 2027"

    return (
        Workflow("ai-research-pipeline")
        .add(Node(
            "research",
            agent=agents["researcher"],
            prompt=f"Research this topic: {topic}. Provide 5 key findings.",
        ))
        .add(Node(
            "analyze",
            agent=agents["analyst"],
            prompt="Analyze the research findings. Identify the 3 most impactful "
                   "implications and rate their likelihood (1-10).",
        ).depends_on("research"))
        .add(Node(
            "summarize",
            agent=agents["writer"],
            prompt="Write a concise executive summary combining the research "
                   "and analysis into a coherent brief.",
        ).depends_on("research").depends_on("analyze"))
    )


# ---------------------------------------------------------------------------
# 3) Scenario: Embedded mode — everything in-process
# ---------------------------------------------------------------------------
def demo_embedded(agents: dict[str, FlintOpenAIAgent]) -> None:
    """Run a workflow in embedded mode.

    The Workflow builder:
    1. Starts a FlintEngine inside your process
    2. Registers your agents (adapters) on the engine
    3. Submits the DAG to the engine
    4. Engine's internal workers execute YOUR adapters locally
    5. Returns results
    """
    print("\n" + "=" * 70)
    print("🔥 SCENARIO 1: Embedded Mode (self-contained, no server needed)")
    print("=" * 70)
    print("  Agents execute inside your process via FlintEngine.\n")

    wf = build_research_pipeline(agents)

    # .run() with no server_url → embedded mode
    results = wf.run(port=5160, timeout=120, verbose=True)

    print("\n📊 Results:")
    for node_id, output in results.items():
        print(f"\n  --- {node_id.upper()} ---")
        print(_indent(output[:400], 4))
        if len(output) > 400:
            print(f"    ... ({len(output)} chars total)")


# ---------------------------------------------------------------------------
# 4) Scenario: Remote mode — client provides agents, server orchestrates
# ---------------------------------------------------------------------------
def demo_remote(agents: dict[str, FlintOpenAIAgent], server_url: str) -> None:
    """Run a workflow against a running Flint server.

    The Workflow builder:
    1. Starts a FlintWorker on YOUR machine
    2. Registers your agents (adapters) on the worker
    3. Submits the DAG definition to the server
    4. Worker claims tasks from server, executes locally, reports results back
    5. Server handles DAG advancement, retries, DLQ
    6. Returns results
    """
    print("\n" + "=" * 70)
    print(f"🌐 SCENARIO 2: Remote Mode (server at {server_url})")
    print("=" * 70)
    print("  Agents execute on YOUR machine; server only orchestrates.\n")

    wf = build_research_pipeline(agents)

    # .run(server_url=...) → remote mode with FlintWorker
    results = wf.run(server_url=server_url, timeout=180, verbose=True)

    print("\n📊 Results:")
    for node_id, output in results.items():
        print(f"\n  --- {node_id.upper()} ---")
        print(_indent(output[:400], 4))
        if len(output) > 400:
            print(f"    ... ({len(output)} chars total)")

    # Show dashboard after workflow completes
    demo_dashboard(server_url)


# ---------------------------------------------------------------------------
# 5) Scenario: Standalone FlintWorker — long-running agent executor
# ---------------------------------------------------------------------------
def demo_standalone_worker(
    agents: dict[str, FlintOpenAIAgent], server_url: str
) -> None:
    """Start a standalone FlintWorker that continuously polls the server.

    This is the production pattern:
    - Server runs in Docker/K8s (handles queuing, DAG, retries, dashboard)
    - Worker runs on your machine or a GPU box (executes agents with your API keys)
    - Multiple workers can connect to the same server for horizontal scaling

    Submit workflows via curl or the UI, workers pick them up automatically.
    """
    from flint_ai.worker import FlintWorker

    print("\n" + "=" * 70)
    print(f"⚡ STANDALONE WORKER MODE (server at {server_url})")
    print("=" * 70)
    print("  Worker claims tasks from the server and executes agents locally.")
    print("  Submit tasks via the dashboard or curl. Press Ctrl+C to stop.\n")

    worker = FlintWorker(server_url)
    for name, agent in agents.items():
        worker.register(name, agent)
        print(f"  ✅ Registered agent: {name}")

    print(f"\n  Polling {server_url} for tasks...\n")

    # Blocks until Ctrl+C
    worker.start(poll_interval=1.0, concurrency=4, block=True)


# ---------------------------------------------------------------------------
# 6) Dashboard query — show server stats
# ---------------------------------------------------------------------------
def demo_dashboard(server_url: str) -> None:
    """Query the server dashboard after running workflows."""
    print("\n" + "=" * 70)
    print("📊 DASHBOARD & MONITORING")
    print("=" * 70)

    client = httpx.Client(base_url=server_url, timeout=10)
    try:
        r = client.get("/dashboard/summary")
        if r.status_code == 200:
            s = r.json()
            print(f"  Total tasks:  {s['total']}")
            print(f"  By state:     {json.dumps(s['by_state'])}")
            print(f"  Queue depth:  {s['queue_length']}")
            print(f"  DLQ depth:    {s['dlq_length']}")
            print(f"  Workers:      {s['worker_count']}")

        r = client.get("/dashboard/concurrency")
        if r.status_code == 200:
            print(f"  Concurrency:  {json.dumps(r.json())}")

        r = client.get("/health")
        if r.status_code == 200:
            print(f"  Health:       {r.json()['status']}")

        print(f"\n  🖥  Dashboard UI → {server_url}/ui/")
        print(f"  📖 Swagger docs → {server_url}/docs")
        print(f"  📈 Grafana      → http://localhost:3000 (if monitoring stack)")
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _indent(text: str, n: int) -> str:
    pad = " " * n
    return "\n".join(pad + line for line in text.strip().split("\n"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Real AI Workflow — Flint with actual OpenAI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Embedded mode (no server needed)
  OPENAI_API_KEY=sk-... python examples/real_ai_workflow.py

  # Against a running server
  OPENAI_API_KEY=sk-... python examples/real_ai_workflow.py --server http://localhost:5156

  # Standalone worker (polls server for tasks)
  OPENAI_API_KEY=sk-... python examples/real_ai_workflow.py --worker http://localhost:5156
        """,
    )
    parser.add_argument(
        "--server", type=str, default=None,
        help="URL of a running Flint server for remote mode.",
    )
    parser.add_argument(
        "--worker", type=str, default=None,
        help="URL of a running Flint server — starts a standalone worker.",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable is required.")
        print("   export OPENAI_API_KEY=sk-...")
        sys.exit(1)

    agents = create_agents()
    print(f"✅ Created {len(agents)} agents: {', '.join(agents.keys())}")

    if args.worker:
        demo_standalone_worker(agents, args.worker)
    elif args.server:
        demo_remote(agents, args.server)
    else:
        demo_embedded(agents)


if __name__ == "__main__":
    main()
