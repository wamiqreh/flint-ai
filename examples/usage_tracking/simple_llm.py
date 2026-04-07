"""Simple LLM call with unified usage tracking.

Demonstrates the core pipeline:
    OpenAIAdapter → Normalizer → CostEngine → EventEmitter → Aggregator

Run: python examples/usage_tracking/simple_llm.py
"""

from __future__ import annotations

import asyncio

from flint_ai.usage import CostEngine, EventEmitter, PricingRegistry
from flint_ai.usage.aggregator import Aggregator
from flint_ai.usage.adapters.openai import OpenAIAdapter


async def main() -> None:
    pricing = PricingRegistry()
    emitter = EventEmitter()
    aggregator = Aggregator()

    def on_event(event):
        aggregator.add_event(event)
        print(
            f"  [{event.type.value}] {event.provider}:{event.model} "
            f"in={event.input_tokens} out={event.output_tokens} "
            f"cost=${event.cost_usd:.6f} estimated={event.estimated}"
        )

    emitter.subscribe(on_event)

    adapter = OpenAIAdapter(
        api_key="sk-demo-key",
        pricing=pricing,
        emitter=emitter,
    )

    print("=== Simple LLM Call ===")
    print(f"Available models: {pricing.list_models('openai')[:5]}...")

    result = await adapter.execute_llm(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello, world!"}],
    )

    print(f"\nResponse: {result.content[:100]}...")
    print(f"Usage: {result.usage.to_dict()}")

    summary = aggregator.by_model()
    print(f"\n=== Aggregation Summary ===")
    for model_key, model_summary in summary.items():
        print(
            f"  {model_key}: ${model_summary.total_cost:.6f} "
            f"({model_summary.call_count} calls, {model_summary.total_tokens} tokens)"
        )

    print(f"\nTotal cost: ${aggregator.total_cost():.6f}")
    print(f"Total tokens: {aggregator.total_tokens()}")


if __name__ == "__main__":
    asyncio.run(main())
