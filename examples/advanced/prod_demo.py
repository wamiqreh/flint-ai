"""Flint AI - Production Demo with Postgres + Redis.

This example runs the full pipeline using:
- PostgreSQL for task/workflow/tool_execution persistence
- Redis for queue, pub/sub, and distributed locking
- The Flint Python SDK (Workflow, Node, AsyncOrchestratorClient)
- OpenAI adapters with cost tracking

Usage:
    docker compose up -d redis postgres
    python examples/advanced/prod_demo.py

Then open:
    http://localhost:5356/ui          - Dashboard
    http://localhost:5356/ui/costs    - Costs
    http://localhost:5356/ui/tools    - Tool Trace
    http://localhost:5356/ui/runs     - Workflow Runs (with DAG)
"""

import os
import sys
import time
import asyncio
from datetime import datetime, timezone

from flint_ai import Workflow, Node, AsyncOrchestratorClient
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.adapters.core.cost_tracker import FlintCostTracker, TimeBoundPrice
from flint_ai import tool


# -- Tools --
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


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: Set OPENAI_API_KEY environment variable.")
        print("  PowerShell: $env:OPENAI_API_KEY = 'sk-...'")
        sys.exit(1)

    # -- Config --
    REDIS_URL = "redis://localhost:6379"
    POSTGRES_URL = "postgresql://flint@localhost:5433/flint"
    SERVER_URL = "http://localhost:5356"

    print("=" * 60)
    print("Flint AI - Production Demo (Postgres + Redis)")
    print("=" * 60)
    print(f"Redis:    {REDIS_URL}")
    print(f"Postgres: {POSTGRES_URL}")
    print(f"Server:   {SERVER_URL}")

    # -- Agent with cost tracker --
    tracker = FlintCostTracker()
    tracker.add_time_bound_price(
        TimeBoundPrice(
            model="gpt-4o-mini",
            prompt_cost_per_million=0.150,
            completion_cost_per_million=0.600,
            effective_from=datetime(2024, 7, 18, tzinfo=timezone.utc),
        )
    )

    agent = FlintOpenAIAgent(
        name="demo-agent",
        model="gpt-4o-mini",
        instructions="You are a helpful assistant. Use tools when asked. Keep responses brief.",
        tools=[get_weather, get_time, search_code],
        cost_tracker=tracker,
    )
    print(f"\nAgent: {agent.name} (model: {agent.model})")
    print(f"Tools: {[t.__name__ for t in agent.tools]}")

    # -- Start embedded server with Postgres + Redis --
    from flint_ai.server import FlintEngine, ServerConfig
    from flint_ai.server.config import RedisConfig, PostgresConfig

    config = ServerConfig(
        port=5356,
        redis=RedisConfig(url=REDIS_URL),
        postgres=PostgresConfig(url=POSTGRES_URL, min_pool_size=1, max_pool_size=5),
        store_backend="postgres",
        queue_backend="redis",
    )

    engine = FlintEngine(config)
    engine.register_adapter(agent)

    print("\nStarting server...")
    engine.start()
    time.sleep(3)
    print(f"Server running at {SERVER_URL}")

    asyncio.run(run_demo(SERVER_URL, agent))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
        engine.stop()
        print("Server stopped.")


# -- Run Demo using SDK --
async def run_demo(server_url: str, agent: FlintOpenAIAgent):
    async with AsyncOrchestratorClient(server_url) as client:
        # -- Workflow 1: Sequential DAG --
        print("\n[Workflow 1] Research Pipeline (research -> analyze -> write)...")

        wf1 = (
            Workflow("research-pipeline")
            .add(Node("research", agent=agent, prompt="Research the topic: best practices for Python async/await."))
            .add(
                Node(
                    "analyze", agent=agent, prompt="Analyze the research results and summarize key findings."
                ).depends_on("research")
            )
            .add(
                Node("write", agent=agent, prompt="Write a short article based on the analysis.").depends_on("analyze")
            )
        )

        # Deploy and start via SDK
        workflow_id = await client.deploy_workflow(wf1)
        print(f"  Deployed: {workflow_id}")

        await client.start_workflow(workflow_id)
        print(f"  Started workflow run")

        # -- Workflow 2: Parallel --
        print("\n[Workflow 2] Info Gathering (weather + time + search in parallel)...")

        wf2 = (
            Workflow("info-gathering")
            .add(Node("weather", agent=agent, prompt="What's the weather in London?"))
            .add(Node("time", agent=agent, prompt="What time is it in Tokyo?"))
            .add(Node("search", agent=agent, prompt="Search for 'python async' in the codebase."))
        )

        workflow_id2 = await client.deploy_workflow(wf2)
        print(f"  Deployed: {workflow_id2}")

        await client.start_workflow(workflow_id2)
        print(f"  Started workflow run")

        # -- Wait for tasks --
        print("\nWaiting for tasks to complete...")
        for i in range(60):
            await asyncio.sleep(2)
            tasks = await client.list_tasks()
            wf1_tasks = [t for t in tasks if t.get("workflow_id") == "research-pipeline"]
            wf2_tasks = [t for t in tasks if t.get("workflow_id") == "info-gathering"]
            done1 = [t for t in wf1_tasks if t["state"] in ("succeeded", "failed", "dead_letter")]
            done2 = [t for t in wf2_tasks if t["state"] in ("succeeded", "failed", "dead_letter")]
            print(f"  Research: {len(done1)}/{len(wf1_tasks)}  |  Info: {len(done2)}/{len(wf2_tasks)}")
            if len(done1) == len(wf1_tasks) and len(done2) == len(wf2_tasks):
                break

        # -- Results --
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        tasks = await client.list_tasks()

        for wf_id in ["research-pipeline", "info-gathering"]:
            wf_tasks = [t for t in tasks if t.get("workflow_id") == wf_id]
            total_cost = 0
            total_tokens = 0
            print(f"\n--- {wf_id} ---")
            for t in wf_tasks:
                cb = t.get("metadata", {}).get("cost_breakdown", {})
                cost = cb.get("total_cost_usd", 0) if cb else 0
                tokens = cb.get("total_tokens", 0) if cb else 0
                total_cost += cost
                total_tokens += tokens
                print(f"  {t['id'][:8]} {t['node_id']:10s} {t['state']:12s} ${cost:.6f}  {tokens} tokens")
            print(f"  Total: ${total_cost:.6f}  {total_tokens} tokens")

        # Tool executions via dashboard API
        import httpx

        async with httpx.AsyncClient(base_url=server_url, timeout=30) as http:
            resp = await http.get("/dashboard/tools/executions")
            execs = resp.json()
            print(f"\nTool Executions: {len(execs)}")
            for e in execs:
                print(f"  {e['tool_name']:15s} {e['status']:10s} {e.get('duration_ms', 0):.1f}ms")

            resp = await http.get("/dashboard/cost/summary")
            summary = resp.json()
            print(
                f"\nCost Summary: ${summary['total_cost_usd']:.6f} | {summary['total_tokens']} tokens | {summary['task_count']} tasks"
            )

        print("\n" + "=" * 60)
        print("VIEW IN BROWSER")
        print("=" * 60)
        print("  Dashboard:  http://localhost:5356/ui")
        print("  Costs:      http://localhost:5356/ui/costs")
        print("  Tools:      http://localhost:5356/ui/tools")
        print("  Runs:       http://localhost:5356/ui/runs")
        print("\nPress Ctrl+C to stop.")


if __name__ == "__main__":
    main()
