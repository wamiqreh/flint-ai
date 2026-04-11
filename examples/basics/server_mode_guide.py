"""Server Mode Guide - Run Flint as a separate process.

This shows how to use Flint in server mode (separate process).
The server runs independently, and you connect via HTTP API.

Server mode is perfect for:
- Production deployments
- Microservices architecture
- Scaling across multiple servers
- Persistent queues (Redis + Postgres)
- Running multiple workers
"""

import time
import httpx


def main():
    print("=" * 70)
    print("  SERVER MODE EXAMPLE")
    print("=" * 70)
    print()

    print("  STEP 1: Start the server in a separate terminal")
    print("  ─" * 35)
    print()
    print("  Terminal 1 (Server):")
    print("  $ python -m flint_ai.server.run --port 5160")
    print()
    print("  Optional flags:")
    print("  --queue redis://localhost:6379        # Use Redis queue")
    print("  --store postgres://localhost/flint_db  # Use Postgres store")
    print("  --workers 4                            # Number of workers")
    print()

    # Connect to server
    base_url = "http://localhost:5160"
    print("  STEP 2: Connect from your app (this terminal)")
    print("  ─" * 35)
    print()

    try:
        client = httpx.Client(base_url=base_url, timeout=5)

        # Health check
        print("  Checking server health...")
        r = client.get("/health")
        health = r.json()
        print(f"  ✓ Server is running: {health['status']}")
        print()

        # Submit task
        print("  Submitting task...")
        r = client.post("/tasks", json={
            "agent_type": "dummy",
            "prompt": "Process customer data",
        })
        task = r.json()
        task_id = task["id"]
        print(f"  ✓ Task submitted: {task_id[:12]}...")
        print()

        # Wait for processing
        print("  Waiting for task to complete...")
        for i in range(10):
            time.sleep(0.5)
            r = client.get(f"/tasks/{task_id}")
            task = r.json()
            state = task["state"]
            print(f"    [{i}] State: {state}")
            if state in ["completed", "failed"]:
                break
        print()

        # Get result
        print("  Task result:")
        print(f"  Result: {task.get('result', 'N/A')[:100]}")
        print()

    except httpx.ConnectError:
        print("  ERROR: Server not running!")
        print("  Start server first: python -m flint_ai.server.run --port 5160")
        print()
        return

    # Show dashboard URLs
    print("  STEP 3: Explore the dashboard")
    print("  ─" * 35)
    print()
    print(f"  Main dashboard:  {base_url}/ui/")
    print(f"  Swagger API:     {base_url}/docs")
    print(f"  Costs:           {base_url}/ui/costs")
    print(f"  Tools:           {base_url}/ui/tools")
    print(f"  Runs:            {base_url}/ui/runs")
    print()

    print("=" * 70)
    print("  KEY POINTS:")
    print("  - Server runs in separate process")
    print("  - Connect via HTTP API from any app/language")
    print("  - State persists (with Redis + Postgres)")
    print("  - Scales across multiple machines")
    print("  - Multiple workers can process tasks in parallel")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
