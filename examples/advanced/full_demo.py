"""Flint AI — Comprehensive Demo: Cost Tracking + Tool Logging + Workflows.

This example demonstrates the full pipeline:
1. Define tools (weather, time, code search)
2. Create an OpenAI agent with those tools
3. Build a workflow with connected nodes (DAG)
4. Submit and run the workflow
5. View cost breakdown, tool executions, and task details
6. Start the embedded server so you can explore the UI

Usage:
    $env:OPENAI_API_KEY = "sk-..."
    python examples/full_demo.py

Then open:
    http://localhost:5356/ui          — Dashboard
    http://localhost:5356/ui/costs    — Costs
    http://localhost:5356/ui/tools    — Tool Trace
    http://localhost:5356/ui/runs     — Workflow Runs (with DAG)
"""

import os
import sys
import time
import asyncio

# ── API Key ──────────────────────────────────────────────────────────────
if not os.environ.get("OPENAI_API_KEY"):
    print("ERROR: Set OPENAI_API_KEY environment variable.")
    print("  PowerShell: $env:OPENAI_API_KEY = 'sk-...'")
    print("  Linux/Mac:  export OPENAI_API_KEY='sk-...'")
    sys.exit(1)

# ── Imports ──────────────────────────────────────────────────────────────
from flint_ai.server import FlintEngine, ServerConfig
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.adapters.core.cost_tracker import FlintCostTracker, TimeBoundPrice
from datetime import datetime, timezone
import httpx

# ── Step 1: Define Tools ────────────────────────────────────────────────
from flint_ai import tool


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Weather in {city}: sunny, 25C, light breeze"


@tool
def get_time(timezone: str) -> str:
    """Get the current time in a timezone."""
    return f"Current time in {timezone}: 14:30 UTC"


@tool
def search_code(query: str) -> str:
    """Search a codebase for a query."""
    return f"Found 3 results for '{query}':\n1. src/main.py:42\n2. src/utils.py:15\n3. src/config.py:8"


# ── Step 2: Create Agent with Custom Cost Tracker ───────────────────────
print("=" * 60)
print("Flint AI - Full Demo")
print("=" * 60)

# Create a cost tracker with time-bound pricing
tracker = FlintCostTracker()

# Example: add a time-bound price (if OpenAI changes pricing, old costs stay correct)
tracker.add_time_bound_price(
    TimeBoundPrice(
        model="gpt-4o-mini",
        prompt_cost_per_million=0.150,
        completion_cost_per_million=0.600,
        effective_from=datetime(2024, 7, 18, tzinfo=timezone.utc),
        effective_to=None,  # still active
    )
)

agent = FlintOpenAIAgent(
    name="demo-agent",
    model="gpt-4o-mini",
    instructions="You are a helpful assistant. Use tools when asked. Keep responses brief.",
    tools=[get_weather, get_time, search_code],
    cost_tracker=tracker,
)
print(f"Agent: {agent.name} (model: {agent.model})")
print(f"Tools: {[t.__name__ for t in agent.tools]}")

# ── Step 3: Start Embedded Server ──────────────────────────────────────
print("\nStarting server on port 5356...")
engine = FlintEngine(ServerConfig(port=5356))
engine.register_adapter(agent)
engine.start()
time.sleep(3)
print(f"Server running at http://localhost:5356")


# ── Step 4: Create Workflows ────────────────────────────────────────────
async def run_demo():
    async with httpx.AsyncClient(base_url="http://localhost:5356", timeout=60) as client:
        # Wait for agent registration
        for i in range(20):
            await asyncio.sleep(0.5)
            try:
                resp = await client.get("/agents")
                agents = resp.json()
                if any(a["agent_type"] == "demo-agent" for a in agents):
                    break
            except Exception:
                pass

        # ── Workflow 1: Research Pipeline (sequential DAG) ──────────────
        print("\n[Workflow 1] Creating Research Pipeline (research -> analyze -> write)...")
        wf1 = {
            "id": "research-pipeline",
            "name": "Research Pipeline",
            "nodes": [
                {
                    "id": "research",
                    "agent_type": "demo-agent",
                    "prompt_template": "Research the topic: best practices for Python async/await.",
                },
                {
                    "id": "analyze",
                    "agent_type": "demo-agent",
                    "prompt_template": "Analyze the research results and summarize key findings.",
                },
                {
                    "id": "write",
                    "agent_type": "demo-agent",
                    "prompt_template": "Write a short article based on the analysis.",
                },
            ],
            "edges": [
                {"from_node_id": "research", "to_node_id": "analyze"},
                {"from_node_id": "analyze", "to_node_id": "write"},
            ],
        }
        resp = await client.post("/workflows", json=wf1)
        print(f"  Created: {resp.json()['id']}")

        resp = await client.post("/workflows/research-pipeline/start", json={})
        run1 = resp.json()
        print(f"  Run: {run1['id'][:8]}... state={run1['state']}")
        print(f"  Tasks: {run1.get('task_ids', {})}")

        # ── Workflow 2: Info Gathering (parallel nodes) ─────────────────
        print("\n[Workflow 2] Creating Info Gathering (weather + time + search in parallel)...")
        wf2 = {
            "id": "info-gathering",
            "name": "Info Gathering",
            "nodes": [
                {"id": "weather", "agent_type": "demo-agent", "prompt_template": "What's the weather in London?"},
                {"id": "time", "agent_type": "demo-agent", "prompt_template": "What time is it in Tokyo?"},
                {
                    "id": "search",
                    "agent_type": "demo-agent",
                    "prompt_template": "Search for 'python async' in the codebase.",
                },
            ],
            "edges": [],  # No edges = all run in parallel
        }
        resp = await client.post("/workflows", json=wf2)
        print(f"  Created: {resp.json()['id']}")

        resp = await client.post("/workflows/info-gathering/start", json={})
        run2 = resp.json()
        print(f"  Run: {run2['id'][:8]}... state={run2['state']}")

        # ── Wait for all tasks to complete ──────────────────────────────
        print("\nWaiting for tasks to complete...")
        for i in range(60):
            await asyncio.sleep(2)
            resp = await client.get("/tasks")
            all_tasks = resp.json()
            wf1_tasks = [t for t in all_tasks if t.get("workflow_id") == "research-pipeline"]
            wf2_tasks = [t for t in all_tasks if t.get("workflow_id") == "info-gathering"]
            done1 = [t for t in wf1_tasks if t["state"] in ("succeeded", "failed", "dead_letter")]
            done2 = [t for t in wf2_tasks if t["state"] in ("succeeded", "failed", "dead_letter")]
            print(f"  Research: {len(done1)}/{len(wf1_tasks)}  |  Info: {len(done2)}/{len(wf2_tasks)}")
            if len(done1) == len(wf1_tasks) and len(done2) == len(wf2_tasks):
                break

        # ── Show Results ────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        resp = await client.get("/tasks")
        all_tasks = resp.json()

        for wf_id in ["research-pipeline", "info-gathering"]:
            tasks = [t for t in all_tasks if t.get("workflow_id") == wf_id]
            total_cost = 0
            total_tokens = 0
            print(f"\n--- {wf_id} ---")
            for t in tasks:
                cb = t.get("metadata", {}).get("cost_breakdown", {})
                cost = cb.get("total_cost_usd", 0) if cb else 0
                tokens = cb.get("total_tokens", 0) if cb else 0
                total_cost += cost
                total_tokens += tokens
                print(f"  {t['id'][:8]} {t['node_id']:10s} {t['state']:12s} ${cost:.6f}  {tokens} tokens")
            print(f"  Total: ${total_cost:.6f}  {total_tokens} tokens")

        # Tool executions
        resp = await client.get("/dashboard/tools/executions")
        execs = resp.json()
        print(f"\nTool Executions: {len(execs)}")
        for e in execs:
            print(f"  {e['tool_name']:15s} {e['status']:10s} {e.get('duration_ms', 0):.1f}ms")

        # Cost summary
        resp = await client.get("/dashboard/cost/summary")
        summary = resp.json()
        print(
            f"\nCost Summary: ${summary['total_cost_usd']:.6f}  |  {summary['total_tokens']} tokens  |  {summary['task_count']} tasks"
        )

        # ── UI URLs ─────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("VIEW IN BROWSER")
        print("=" * 60)
        print("  Dashboard:  http://localhost:5356/ui")
        print("  Costs:      http://localhost:5356/ui/costs")
        print("  Tools:      http://localhost:5356/ui/tools")
        print("  Runs:       http://localhost:5356/ui/runs")
        print("\n  In the Runs page:")
        print("    - Click a workflow card to see its runs")
        print("    - Click a run to see DAG with arrows, costs, and tool calls")
        print("    - Click a task row to expand details (lazy-loaded)")
        print("    - Click 'Load tool executions' per task")
        print("\nPress Ctrl+C to stop the server.")


asyncio.run(run_demo())

# -- Keep server running --
if __name__ == "__main__":
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
        engine.stop()
        print("Server stopped.")
