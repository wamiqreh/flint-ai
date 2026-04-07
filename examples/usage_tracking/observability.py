"""Demonstrates real-time event streaming and observability hooks.

Shows how to:
- Listen to events in real-time
- Stream events asynchronously
- Get human-readable debug logs

Run: python examples/usage_tracking/observability.py
"""

from __future__ import annotations

import asyncio

from flint_ai.usage import CostEngine, EventEmitter, EventType, ObservabilityHooks, PricingRegistry
from flint_ai.usage.normalizer import Normalizer


async def main() -> None:
    pricing = PricingRegistry()
    emitter = EventEmitter()
    hooks = ObservabilityHooks()
    normalizer = Normalizer()
    cost_engine = CostEngine(pricing)

    hooks.add_listener(lambda e: print(f"  [HOOK] {hooks.debug_log(e)}"))

    def on_event(event):
        asyncio.create_task(hooks.on_event(event))

    emitter.subscribe(on_event)

    print("=== Observability Demo ===\n")

    events_to_emit = [
        normalizer.normalize_llm(
            provider="openai",
            model="gpt-4o",
            input_text="Write a poem about AI",
            output_text="In circuits and code, a mind awakes...",
            usage={"prompt_tokens": 15, "completion_tokens": 20},
        ),
        normalizer.normalize_embedding(
            provider="openai",
            model="text-embedding-3-small",
            input_text="Sample text for embedding",
            usage={"prompt_tokens": 6},
        ),
        normalizer.normalize_image(
            provider="openai",
            model="dall-e-3",
            image_count=2,
            metadata={"prompt": "A futuristic city"},
        ),
    ]

    for event in events_to_emit:
        cost = cost_engine.calculate(event)
        event = event.with_cost(cost)
        await emitter.emit_async(event)
        await asyncio.sleep(0.05)

    print(f"\n=== Debug Log ===")
    for event in events_to_emit:
        print(f"  {hooks.debug_log(event)}")

    print(f"\n=== Cost Explanations ===")
    for event in events_to_emit:
        explanation = cost_engine.explain_cost(event)
        print(f"\n{explanation.summary()}")


if __name__ == "__main__":
    asyncio.run(main())
