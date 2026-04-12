"""Workflow with Cost Tracking.

Same 3-node pipeline as 01, but with an OpenAI agent and automatic cost tracking.
Cost is sourced from the centralized CostConfigManager (DB or defaults).

Requires: OPENAI_API_KEY environment variable.
Run: python examples/quickstart/02_with_cost_tracking.py
"""

import os

from flint_ai import Node, Workflow
from flint_ai.adapters.openai import FlintOpenAIAgent

if not os.environ.get("OPENAI_API_KEY"):
    print("Set OPENAI_API_KEY first: $env:OPENAI_API_KEY = 'sk-...'")
    exit(1)

# Create agent — cost tracking is enabled by default
agent = FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini", instructions="Summarize the input.")

workflow = (
    Workflow("cost-demo")
    .add(Node("summarize", agent=agent, prompt="Summarize: The quick brown fox jumps over the lazy dog"))
)

print("Running workflow with cost tracking...")
results = workflow.run()

for node_id, result in results.items():
    print(f"  {node_id}: {result[:80]}...")

print("\nDone! View costs at http://localhost:5160/ui/costs")
