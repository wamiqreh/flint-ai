"""Example: Multimodal Cost Tracking (Embeddings + Images).

Demonstrates how to track costs for:
1. Text embeddings (OpenAI text-embedding-3 models)
2. Image generation (DALL-E 3)
3. Vision/image analysis (GPT-4 Vision)

Shows the unified CostEngine calculating costs for different modalities.
"""

import asyncio
import time

from flint_ai.usage import CostEngine, EventEmitter, PricingRegistry
from flint_ai.usage.events import AIEvent, EventType


async def main():
    """Demonstrate multimodal cost tracking."""
    
    # ── Setup ─────────────────────────────────────────────────────────────
    pricing = PricingRegistry()
    engine = CostEngine(pricing)
    emitter = EventEmitter()
    
    print("=" * 70)
    print("FLINT AI: Multimodal Cost Tracking Example")
    print("=" * 70)
    
    # Track all events
    events_summary = {"embedding": [], "image": [], "llm": []}
    
    def on_event(event: AIEvent):
        """Track events by type."""
        if event.type == EventType.EMBEDDING:
            events_summary["embedding"].append(event)
        elif event.type == EventType.IMAGE:
            events_summary["image"].append(event)
        elif event.type == EventType.LLM_CALL:
            events_summary["llm"].append(event)
    
    emitter.subscribe(on_event)
    
    # ── 1. Embedding Cost (Text Embeddings) ────────────────────────────────
    print("\n[1] TEXT EMBEDDING COST")
    print("-" * 70)
    
    # Small embedding model
    embedding_small = AIEvent(
        provider="openai",
        model="text-embedding-3-small",
        type=EventType.EMBEDDING,
        input_tokens=5000,  # 5000 tokens to embed
    )
    
    cost_small = engine.calculate(embedding_small)
    emitter.emit(embedding_small)
    
    print(f"Model: text-embedding-3-small")
    print(f"Input tokens: {embedding_small.input_tokens:,}")
    print(f"Cost: ${cost_small:.6f}")
    
    # Large embedding model
    embedding_large = AIEvent(
        provider="openai",
        model="text-embedding-3-large",
        type=EventType.EMBEDDING,
        input_tokens=5000,
    )
    
    cost_large = engine.calculate(embedding_large)
    emitter.emit(embedding_large)
    
    print(f"\nModel: text-embedding-3-large")
    print(f"Input tokens: {embedding_large.input_tokens:,}")
    print(f"Cost: ${cost_large:.6f}")
    
    # ── 2. Image Generation Cost (DALL-E 3) ────────────────────────────────
    print("\n[2] IMAGE GENERATION COST (DALL-E 3)")
    print("-" * 70)
    
    image_event = AIEvent(
        provider="openai",
        model="dall-e-3",
        type=EventType.IMAGE,
        metadata={
            "image_count": 3,  # 3 images generated
            "size": "1024x1024",
            "quality": "standard",
        },
    )
    
    cost_images = engine.calculate(image_event)
    emitter.emit(image_event)
    
    print(f"Model: dall-e-3")
    print(f"Images generated: {image_event.metadata.get('image_count', 0)}")
    print(f"Size: {image_event.metadata.get('size', 'unknown')}")
    print(f"Cost per image: ${0.04:.4f}")
    print(f"Total cost: ${cost_images:.6f}")
    
    # ── 3. Vision Analysis Cost (GPT-4 Vision) ────────────────────────────
    print("\n[3] VISION ANALYSIS COST (GPT-4 with Vision)")
    print("-" * 70)
    
    vision_event = AIEvent(
        provider="openai",
        model="gpt-4o",
        type=EventType.LLM_CALL,
        input_tokens=2000,  # image tokens
        output_tokens=500,  # text output
        metadata={
            "image_count": 2,  # 2 images analyzed
            "image_type": "base64",
            "use_case": "vision",
        },
    )
    
    cost_vision = engine.calculate(vision_event)
    emitter.emit(vision_event)
    
    print(f"Model: gpt-4o")
    print(f"Input tokens (with images): {vision_event.input_tokens:,}")
    print(f"Output tokens: {vision_event.output_tokens:,}")
    print(f"Cost: ${cost_vision:.6f}")
    
    # ── Summary ───────────────────────────────────────────────────────────
    print("\n[SUMMARY]")
    print("=" * 70)
    
    total_embedding_cost = cost_small + cost_large
    total_cost = total_embedding_cost + cost_images + cost_vision
    
    print(f"[OK] Embeddings (2 calls):        ${total_embedding_cost:.6f}")
    print(f"[OK] Image generation (1 call):  ${cost_images:.6f}")
    print(f"[OK] Vision analysis (1 call):   ${cost_vision:.6f}")
    print(f"{'-' * 70}")
    print(f"Total multimodal cost:         ${total_cost:.6f}")
    print(f"Total events emitted:          {len(events_summary['embedding']) + len(events_summary['image']) + len(events_summary['llm'])}")
    
    print("\n[SUCCESS] Multimodal cost tracking complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
