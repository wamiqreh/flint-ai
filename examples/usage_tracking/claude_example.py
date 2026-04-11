"""Example: Claude with unified cost tracking system.

Shows how to use Claude (Anthropic) via the new usage tracking system
with automatic cost calculation and event emission.
"""

import asyncio

from flint_ai.usage import CostEngine, EventEmitter, PricingRegistry
from flint_ai.usage.adapters.anthropic import AnthropicAdapter


async def main():
    """Run Claude with cost tracking."""
    # Setup: pricing registry and event emitter
    pricing = PricingRegistry()
    emitter = EventEmitter()

    # Create adapter
    adapter = AnthropicAdapter(
        api_key="sk-ant-...",  # Set ANTHROPIC_API_KEY env var
        pricing=pricing,
        emitter=emitter,
    )

    # Track events
    events = []

    async def on_event(event):
        events.append(event)
        print(f"[EVENT] {event.provider}:{event.model} - {event.type}")

    emitter.add_listener(on_event)

    # Execute LLM call
    result = await adapter.execute_llm(
        model="claude-3-5-sonnet-20241022",
        messages=[
            {"role": "user", "content": "What is the capital of France?"}
        ],
        system="You are a helpful assistant.",
        max_tokens=100,
    )

    # Display results
    print(f"\n{'='*60}")
    print(f"Response: {result.content}")
    print(f"Input tokens: {result.usage.input_tokens}")
    print(f"Output tokens: {result.usage.output_tokens}")
    print(f"Total cost: ${result.cost_usd:.6f}")
    print(f"{'='*60}\n")

    # Show all events
    print(f"Events emitted: {len(events)}")
    for event in events:
        print(f"  - {event.event_id}: {event.type}")


if __name__ == "__main__":
    asyncio.run(main())
