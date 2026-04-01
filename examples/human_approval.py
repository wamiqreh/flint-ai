"""Workflow with a human approval gate.

Usage:
    OPENAI_API_KEY=sk-... python examples/human_approval.py

Flow: research → approval (pauses) → write → review
The approval node blocks until a human approves via the dashboard UI or API.
"""

from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(
    name="researcher", model="gpt-4o-mini",
    instructions="Research the topic thoroughly.",
)
writer = FlintOpenAIAgent(
    name="writer", model="gpt-4o-mini",
    instructions="Write a polished summary from the research.",
)
reviewer = FlintOpenAIAgent(
    name="reviewer", model="gpt-4o-mini",
    instructions="Review and score the article out of 10.",
    response_format={"type": "json_object"},
)


def approval_callback(run_id: str, node_id: str, api_url: str) -> bool:
    """Called when a human-approval node is reached. Return True to approve."""
    print(f"\n🔒 Node '{node_id}' requires approval.")
    print(f"   Approve via UI: {api_url}/ui/")
    response = input("   Approve? [Y/n]: ").strip().lower()
    return response != "n"


results = (
    Workflow("approval-demo")
    .add(Node("research", agent=researcher, prompt="Quantum computing breakthroughs 2025"))
    .add(Node("gate", agent="dummy", prompt="Approval checkpoint").depends_on("research").requires_approval())
    .add(Node("write", agent=writer, prompt="Summarize the research").depends_on("gate"))
    .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
    .run(on_approval=approval_callback)
)

for name, output in results.items():
    print(f"\n{'─'*40}\n🔹 {name}:\n{output[:200]}")
