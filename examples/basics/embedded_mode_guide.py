"""Embedded Mode Guide - Run Flint server in-process (like Hangfire).

This shows how to use Flint embedded mode in your Python application.
The server runs as a background thread, so your app keeps running normally.

Embedded mode is perfect for:
- Development and testing
- Demos and POCs
- Applications that want integrated task queue (no separate server)
- Local development with persistence (Redis/Postgres optional)
"""

import time
import httpx

from flint_ai.server import FlintEngine, ServerConfig


def main():
    print("=" * 70)
    print("  EMBEDDED MODE EXAMPLE - Flint Server In-Process")
    print("=" * 70)
    print()

    # ── Step 1: Create and start the engine in background ─────────────────
    print("[1/5] Creating Flint engine...")
    config = ServerConfig(port=5160)
    engine = FlintEngine(config)

    print("[2/5] Starting engine in background (blocking=False)...")
    engine.start(blocking=False)  # ← Runs in background thread

    print(f"      ✓ Engine started at {engine.url}")
    print(f"      ✓ Dashboard: {engine.url}/ui/")
    print()

    # Wait for server to be ready
    time.sleep(1)

    # ── Step 2: Use the engine via HTTP API ───────────────────────────────
    print("[3/5] Submitting tasks via HTTP API...")
    client = httpx.Client(base_url=engine.url)

    # Health check
    r = client.get("/health")
    print(f"      Health: {r.json()['status']}")

    # Submit a task
    r = client.post("/tasks", json={
        "agent_type": "dummy",
        "prompt": "Process order #12345",
    })
    task_id = r.json()["id"]
    print(f"      Task submitted: {task_id[:12]}...")

    # Wait for processing
    time.sleep(2)

    # Check result
    r = client.get(f"/tasks/{task_id}")
    task = r.json()
    print(f"      Task result: state={task['state']}, result={task.get('result', 'N/A')[:50]}")
    print()

    # ── Step 3: Create and run a workflow ─────────────────────────────────
    print("[4/5] Creating and running a workflow...")
    workflow = {
        "id": "demo-pipeline",
        "name": "Demo Pipeline",
        "nodes": [
            {"id": "step1", "agent_type": "dummy", "prompt_template": "Extract data"},
            {"id": "step2", "agent_type": "dummy", "prompt_template": "Transform data"},
            {"id": "step3", "agent_type": "dummy", "prompt_template": "Load data"},
        ],
        "edges": [
            {"from_node_id": "step1", "to_node_id": "step2"},
            {"from_node_id": "step2", "to_node_id": "step3"},
        ],
    }

    r = client.post("/workflows", json=workflow)
    print(f"      Workflow created: {r.json()['id']}")

    # Run workflow
    r = client.post("/workflows/demo-pipeline/start", json={})
    run_id = r.json()["id"]
    print(f"      Workflow started: {run_id[:12]}...")

    # Wait and check
    time.sleep(3)
    r = client.get(f"/workflows/runs/{run_id}")
    run = r.json()
    print(f"      Run state: {run['state']}")
    print(f"      Node progress: {run['node_states']}")
    print()

    # ── Step 4: View dashboard ────────────────────────────────────────────
    print("[5/5] Dashboard is ready!")
    print(f"      Main dashboard:  {engine.url}/ui/")
    print(f"      Swagger API:     {engine.url}/docs")
    print(f"      Costs:           {engine.url}/ui/costs")
    print(f"      Tools:           {engine.url}/ui/tools")
    print(f"      Runs:            {engine.url}/ui/runs")
    print()

    print("=" * 70)
    print("  KEY POINTS:")
    print("  - Server runs in background (blocking=False)")
    print("  - Your app continues running normally")
    print("  - Access via HTTP API (httpx, requests, curl, etc.)")
    print("  - State is in-memory by default (lost on restart)")
    print("  - Can use Redis + Postgres for persistence")
    print("=" * 70)
    print()

    # Keep app running so you can explore dashboard
    print("Press Ctrl+C to stop...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("[SHUTDOWN] Stopping engine...")
        engine.stop()
        print("[SHUTDOWN] Done.")


if __name__ == "__main__":
    main()
