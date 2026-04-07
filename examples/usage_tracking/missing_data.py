"""Demonstrates token estimation fallback when usage data is missing.

Shows how the system handles missing/partial usage data gracefully
by falling back to estimation and marking events as estimated.

Run: python examples/usage_tracking/missing_data.py
"""

from __future__ import annotations

from flint_ai.usage import CostEngine, EventEmitter, PricingRegistry
from flint_ai.usage.aggregator import Aggregator
from flint_ai.usage.estimation import TokenEstimator
from flint_ai.usage.normalizer import Normalizer


def main() -> None:
    pricing = PricingRegistry()
    emitter = EventEmitter()
    aggregator = Aggregator()
    normalizer = Normalizer()
    cost_engine = CostEngine(pricing)

    def on_event(event):
        aggregator.add_event(event)
        marker = "[ESTIMATED]" if event.estimated else "[ACTUAL]"
        print(
            f"  {marker} {event.provider}:{event.model} "
            f"in={event.input_tokens} out={event.output_tokens} "
            f"cost=${event.cost_usd:.6f}"
        )

    emitter.subscribe(on_event)

    import asyncio

    async def run() -> None:
        print("=== Missing Data Handling ===\n")

        print("1. Simulating LLM call with NO usage data (estimation fallback):")
        event = normalizer.normalize_llm(
            provider="openai",
            model="gpt-4o",
            input_text="Explain quantum computing in simple terms",
            output_text="Quantum computing uses quantum mechanics principles...",
            usage=None,
        )
        cost = cost_engine.calculate(event)
        event = event.with_cost(cost)
        await emitter.emit_async(event)

        print("\n2. Simulating LLM call WITH usage data (actual):")
        event = normalizer.normalize_llm(
            provider="openai",
            model="gpt-4o",
            input_text="What is the capital of France?",
            output_text="The capital of France is Paris.",
            usage={"prompt_tokens": 12, "completion_tokens": 8},
        )
        cost = cost_engine.calculate(event)
        event = event.with_cost(cost)
        await emitter.emit_async(event)

        print("\n3. Simulating embedding call with estimation:")
        event = normalizer.normalize_embedding(
            provider="openai",
            model="text-embedding-3-small",
            input_text="This is a sample text for embedding generation with no usage data",
            usage=None,
        )
        cost = cost_engine.calculate(event)
        event = event.with_cost(cost)
        await emitter.emit_async(event)

        print("\n=== Summary ===")
        print(f"Total events: {aggregator.event_count}")
        print(f"Actual events: {sum(1 for e in aggregator.all_events() if not e.estimated)}")
        print(f"Estimated events: {sum(1 for e in aggregator.all_events() if e.estimated)}")
        print(f"Total cost: ${aggregator.total_cost():.6f}")

        print("\n=== Cost Explanation ===")
        for event in aggregator.all_events():
            explanation = cost_engine.explain_cost(event)
            print(f"\nEvent {event.id}:")
            print(explanation.summary())

    asyncio.run(run())


if __name__ == "__main__":
    main()
