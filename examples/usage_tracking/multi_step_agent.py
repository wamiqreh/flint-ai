"""Multi-step agent workflow with per-step cost tracking.

Demonstrates:
- Per-step cost aggregation
- Agent traces
- Retry-aware cost tracking

Run: python examples/usage_tracking/multi_step_agent.py
"""

from __future__ import annotations

import asyncio

from flint_ai.usage import AIEvent, Aggregator, CostEngine, EventEmitter, EventType, PricingRegistry
from flint_ai.usage.adapters.openai import OpenAIAdapter


async def main() -> None:
    pricing = PricingRegistry()
    emitter = EventEmitter()
    aggregator = Aggregator()

    def on_event(event):
        aggregator.add_event(event)

    emitter.subscribe(on_event)

    adapter = OpenAIAdapter(
        api_key="sk-demo-key",
        pricing=pricing,
        emitter=emitter,
    )

    print("=== Multi-Step Agent Workflow ===\n")

    steps = [
        {"node_id": "research", "prompt": "Research the topic of AI safety"},
        {"node_id": "analyze", "prompt": "Analyze the research findings"},
        {"node_id": "write", "prompt": "Write a summary report"},
    ]

    for step in steps:
        print(f"--- Step: {step['node_id']} ---")
        try:
            result = await adapter.execute_llm(
                model="gpt-4o",
                messages=[{"role": "user", "content": step["prompt"]}],
            )
            events = aggregator.by_task(step["node_id"])
            for event in events:
                event = event.with_metadata(node_id=step["node_id"])
            print(f"  Cost: ${aggregator.total_cost():.6f}")
        except Exception as e:
            print(f"  Error (expected without real API key): {e}")

    print(f"\n=== Workflow Summary ===")
    print(f"Total events: {aggregator.event_count}")
    print(f"Total cost: ${aggregator.total_cost():.6f}")
    print(f"Total tokens: {aggregator.total_tokens()}")

    by_model = aggregator.by_model()
    print(f"\nBy model:")
    for model_key, summary in by_model.items():
        print(f"  {model_key}: ${summary.total_cost:.6f} ({summary.call_count} calls)")

    timeline = aggregator.timeline(bucket_minutes=60)
    print(f"\nTimeline ({len(timeline)} buckets):")
    for bucket in timeline:
        print(f"  {bucket['timestamp']}: ${bucket['cost_usd']:.6f} ({bucket['event_count']} events)")


if __name__ == "__main__":
    asyncio.run(main())
