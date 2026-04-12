"""Parallel Branches — Fan-out / Fan-in Pattern.

Runs two nodes in parallel (both depend on the same upstream node),
then merges results in a final node.

No API key required. Uses dummy agents.

Run: python examples/quickstart/05_parallel_branches.py
"""

from flint_ai import Node, Workflow

workflow = (
    Workflow("parallel-pipeline")
    .add(Node("fetch", "dummy", prompt="Fetch data from source"))
    # Fan-out: both analyze and validate run in parallel
    .add(Node("analyze", "dummy", prompt="Analyze the data").depends_on("fetch"))
    .add(Node("validate", "dummy", prompt="Validate the data").depends_on("fetch"))
    # Fan-in: report waits for BOTH analyze AND validate to complete
    .add(Node("report", "dummy", prompt="Write report").depends_on("analyze", "validate"))
)

print("Running parallel workflow (fan-out/fan-in)...")
results = workflow.run()

for node_id, result in results.items():
    print(f"  {node_id}: {result[:80]}...")

print("\nDone!")
