"""Hello Workflow — A simple 3-node pipeline.

No API key required. Uses dummy agents that echo the prompt.

Run: python examples/quickstart/01_hello_workflow.py
"""

from flint_ai import Node, Workflow

# Create a 3-step pipeline: extract -> transform -> load
workflow = (
    Workflow("hello-pipeline")
    .add(Node("extract", "dummy", prompt="Extract data from the input"))
    .add(Node("transform", "dummy", prompt="Transform the extracted data").depends_on("extract"))
    .add(Node("load", "dummy", prompt="Load the transformed data").depends_on("transform"))
)

print("Running workflow...")
results = workflow.run()

for node_id, result in results.items():
    print(f"  {node_id}: {result[:80]}...")

print("\nDone!")
