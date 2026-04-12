"""Human Approval Gates in a Workflow.

Adds a manual approval step between two nodes. The workflow pauses
and calls your approval callback before continuing.

No API key required. Uses dummy agents.

Run: python examples/quickstart/04_approval_gates.py
"""

from flint_ai import Node, Workflow


def approve(node_id: str, upstream_output: str) -> bool:
    """Callback for approval gates. Return True to approve, False to reject."""
    print(f"\n  [APPROVAL] Node '{node_id}' needs approval.")
    print(f"  Upstream output: {upstream_output[:60]}...")
    answer = input("  Approve? (y/n): ").strip().lower()
    return answer == "y"


workflow = (
    Workflow("approval-gate")
    .add(Node("draft", "dummy", prompt="Draft a report"))
    .add(Node("review", "dummy", prompt="Review the draft").depends_on("draft").requires_approval())
    .add(Node("publish", "dummy", prompt="Publish the reviewed report").depends_on("review"))
)

print("Running workflow with approval gate...")
results = workflow.run(on_approval=approve)

for node_id, result in results.items():
    print(f"  {node_id}: {result[:80]}...")

print("\nDone!")
