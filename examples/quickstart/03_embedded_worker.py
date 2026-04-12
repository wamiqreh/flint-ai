"""Embedded Mode with Background Worker.

Shows how to configure poll_interval and adapter_concurrency in embedded mode.
This gives you the full Hangfire-like experience: server + workers in one process.

No API key required. Uses dummy agents.

Run: python examples/quickstart/03_embedded_worker.py
"""

from flint_ai import Node, Workflow

workflow = (
    Workflow("embedded-worker-demo")
    .add(Node("step1", "dummy", prompt="Process step 1"))
    .add(Node("step2", "dummy", prompt="Process step 2").depends_on("step1"))
    .add(Node("step3", "dummy", prompt="Process step 3").depends_on("step2"))
)

print("Running with embedded worker (workers=2, poll_interval=0.5s, concurrency=10)...")
results = workflow.run(
    workers=2,           # Number of background workers
    poll_interval=0.5,   # Queue poll interval in seconds
    adapter_concurrency=10,  # Per-agent concurrency limit
)

for node_id, result in results.items():
    print(f"  {node_id}: {result[:80]}...")

print("\nDone!")
