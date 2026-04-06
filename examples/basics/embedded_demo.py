"""Demo: Flint embedded mode — run the full server inside your Python app (like Hangfire/Celery).

This demonstrates how FlintEngine runs as a background thread in your application,
so you can submit tasks and build workflows without a separate server process.
"""

import asyncio
import time
import httpx

from flint_ai.server import FlintEngine, ServerConfig


def main():
    print("=" * 60)
    print("  Flint Embedded Mode Demo (like Hangfire)")
    print("=" * 60)
    print()

    # 1) Create engine with in-memory backends
    config = ServerConfig(port=5157)
    engine = FlintEngine(config)

    # 2) Start as background thread — your app keeps running
    print("[APP] Starting Flint engine in background...")
    engine.start(blocking=False)
    print(f"[APP] Engine running at {engine.url}")
    print(f"[APP] UI available at {engine.url}/ui/")
    print()

    # 3) Use the API from your app code
    client = httpx.Client(base_url=engine.url)

    # Health check
    r = client.get("/health")
    print(f"[APP] Health check: {r.json()}")

    # Submit tasks
    print("\n[APP] Submitting 3 tasks...")
    task_ids = []
    for i in range(3):
        r = client.post("/tasks", json={
            "agent_type": "dummy",
            "prompt": f"Process order #{i+1}",
        })
        tid = r.json()["id"]
        task_ids.append(tid)
        print(f"  Task {i+1}: {tid[:12]}...")

    # Wait for processing
    print("\n[APP] Waiting for tasks to complete...")
    time.sleep(3)

    # Check results
    print("\n[APP] Task results:")
    for tid in task_ids:
        r = client.get(f"/tasks/{tid}")
        t = r.json()
        print(f"  {tid[:12]}... → state={t['state']}, result={t.get('result', 'N/A')}")

    # Create and run a workflow
    print("\n[APP] Creating a 3-step workflow pipeline...")
    wf = {
        "id": "embedded-pipeline",
        "name": "Embedded Demo Pipeline",
        "nodes": [
            {"id": "extract", "agent_type": "dummy", "prompt_template": "Extract data from source"},
            {"id": "transform", "agent_type": "dummy", "prompt_template": "Transform extracted data"},
            {"id": "load", "agent_type": "dummy", "prompt_template": "Load data into destination"},
        ],
        "edges": [
            {"from_node_id": "extract", "to_node_id": "transform"},
            {"from_node_id": "transform", "to_node_id": "load"},
        ],
    }
    r = client.post("/workflows", json=wf)
    print(f"  Created workflow: {r.json()['id']}")

    r = client.post("/workflows/embedded-pipeline/start", json={})
    run_id = r.json()["id"]
    print(f"  Started run: {run_id[:12]}...")

    # Wait and check run
    time.sleep(5)
    r = client.get(f"/workflows/runs/{run_id}")
    run = r.json()
    print(f"  Run state: {run['state']}")
    print(f"  Node states: {run['node_states']}")

    # Dashboard summary
    print("\n[APP] Dashboard summary:")
    r = client.get("/dashboard/summary")
    s = r.json()
    print(f"  Task counts: {s['task_counts']}")
    print(f"  Workers: {s['worker_count']}")
    print(f"  Queue depth: {s['queue_length']}")

    print(f"\n{'=' * 60}")
    print(f"  UI is live at: {engine.url}/ui/")
    print(f"  Swagger docs at: {engine.url}/docs")
    print(f"  Press Ctrl+C to stop")
    print(f"{'=' * 60}")

    # Keep alive so you can browse the UI
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[APP] Shutting down engine...")
        engine.stop()
        print("[APP] Done.")


if __name__ == "__main__":
    main()
