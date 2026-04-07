"""Cost calculation engine — decoupled from adapters."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from .events import AIEvent, EventType
from .pricing import ModelPricing, PricingRegistry

logger = logging.getLogger("flint.usage.cost_engine")


class CostLineItem(BaseModel):
    """A single line in a cost breakdown."""

    description: str
    tokens: int = 0
    rate_per_1k: float = 0.0
    cost_usd: float = 0.0


class CostExplanation(BaseModel):
    """Human-readable explanation of why an event cost what it did."""

    event_id: str
    model: str
    breakdown: list[CostLineItem]
    total_usd: float

    def summary(self) -> str:
        lines = [f"Cost breakdown for {self.model} (event: {self.event_id}):"]
        for item in self.breakdown:
            lines.append(f"  {item.description}: ${item.cost_usd:.6f}")
        lines.append(f"  Total: ${self.total_usd:.6f}")
        return "\n".join(lines)


class CostEngine:
    """Decoupled cost calculation engine.

    Takes an AIEvent and a PricingRegistry, computes the cost in USD.
    Supports all event types: LLM, embedding, image, audio.

    Usage:
        engine = CostEngine(pricing_registry)
        cost = engine.calculate(event)
        explanation = engine.explain_cost(event)
    """

    def __init__(self, pricing: PricingRegistry) -> None:
        self.pricing = pricing

    def calculate(self, event: AIEvent) -> float:
        """Calculate cost for an AIEvent. Returns cost in USD."""
        pricing = self.pricing.get_pricing(event.provider, event.model)
        if pricing is None:
            logger.warning("No pricing found for %s:%s, returning 0 cost", event.provider, event.model)
            return 0.0

        if event.type == EventType.LLM_CALL:
            return self._calculate_llm(event, pricing)
        if event.type == EventType.EMBEDDING:
            return self._calculate_embedding(event, pricing)
        if event.type == EventType.IMAGE:
            return self._calculate_image(event, pricing)
        if event.type == EventType.AUDIO:
            return self._calculate_audio(event, pricing)
        if event.type == EventType.TOOL_CALL:
            return self._calculate_tool_call(event, pricing)

        return 0.0

    def _calculate_llm(self, event: AIEvent, pricing: ModelPricing) -> float:
        input_tokens = event.input_tokens or 0
        output_tokens = event.output_tokens or 0
        cached_tokens = event.metadata.get("cached_tokens", 0) or 0

        effective_input = input_tokens - cached_tokens
        input_cost = 0.0
        if pricing.input_per_1k is not None and effective_input > 0:
            input_cost = (effective_input / 1_000) * pricing.input_per_1k

        cache_read_cost = 0.0
        if pricing.cache_read_per_1k is not None and cached_tokens > 0:
            cache_read_cost = (cached_tokens / 1_000) * pricing.cache_read_per_1k

        output_cost = 0.0
        if pricing.output_per_1k is not None and output_tokens > 0:
            output_cost = (output_tokens / 1_000) * pricing.output_per_1k

        total = input_cost + cache_read_cost + output_cost
        return round(total, 6)

    def _calculate_embedding(self, event: AIEvent, pricing: ModelPricing) -> float:
        input_tokens = event.input_tokens or 0
        if pricing.embedding_per_1k is None:
            if pricing.input_per_1k is not None:
                return round((input_tokens / 1_000) * pricing.input_per_1k, 6)
            return 0.0
        return round((input_tokens / 1_000) * pricing.embedding_per_1k, 6)

    def _calculate_image(self, event: AIEvent, pricing: ModelPricing) -> float:
        if pricing.per_image is None:
            return 0.0
        count = event.metadata.get("image_count", 1)
        return round(pricing.per_image * count, 6)

    def _calculate_audio(self, event: AIEvent, pricing: ModelPricing) -> float:
        if pricing.per_second_audio is None:
            return 0.0
        duration = event.metadata.get("audio_duration_seconds", 0)
        return round(pricing.per_second_audio * duration, 6)

    def _calculate_tool_call(self, event: AIEvent, pricing: ModelPricing) -> float:
        input_tokens = event.input_tokens or 0
        output_tokens = event.output_tokens or 0

        input_cost = 0.0
        if pricing.input_per_1k is not None and input_tokens > 0:
            input_cost = (input_tokens / 1_000) * pricing.input_per_1k

        output_cost = 0.0
        if pricing.output_per_1k is not None and output_tokens > 0:
            output_cost = (output_tokens / 1_000) * pricing.output_per_1k

        return round(input_cost + output_cost, 6)

    def explain_cost(self, event: AIEvent) -> CostExplanation:
        """Generate a human-readable cost breakdown."""
        pricing = self.pricing.get_pricing(event.provider, event.model)
        if pricing is None:
            return CostExplanation(
                event_id=event.id,
                model=event.model,
                breakdown=[
                    CostLineItem(
                        description="No pricing available",
                        cost_usd=0.0,
                    )
                ],
                total_usd=0.0,
            )

        items: list[CostLineItem] = []
        total = 0.0

        if event.type == EventType.LLM_CALL:
            input_tokens = event.input_tokens or 0
            output_tokens = event.output_tokens or 0
            cached_tokens = event.metadata.get("cached_tokens", 0) or 0
            effective_input = input_tokens - cached_tokens

            if pricing.input_per_1k is not None and effective_input > 0:
                cost = round((effective_input / 1_000) * pricing.input_per_1k, 6)
                items.append(
                    CostLineItem(
                        description=f"Input tokens: {effective_input:,} x ${pricing.input_per_1k}/1K",
                        tokens=effective_input,
                        rate_per_1k=pricing.input_per_1k,
                        cost_usd=cost,
                    )
                )
                total += cost

            if pricing.cache_read_per_1k is not None and cached_tokens > 0:
                cost = round((cached_tokens / 1_000) * pricing.cache_read_per_1k, 6)
                items.append(
                    CostLineItem(
                        description=f"Cache read: {cached_tokens:,} x ${pricing.cache_read_per_1k}/1K",
                        tokens=cached_tokens,
                        rate_per_1k=pricing.cache_read_per_1k,
                        cost_usd=cost,
                    )
                )
                total += cost

            if pricing.output_per_1k is not None and output_tokens > 0:
                cost = round((output_tokens / 1_000) * pricing.output_per_1k, 6)
                items.append(
                    CostLineItem(
                        description=f"Output tokens: {output_tokens:,} x ${pricing.output_per_1k}/1K",
                        tokens=output_tokens,
                        rate_per_1k=pricing.output_per_1k,
                        cost_usd=cost,
                    )
                )
                total += cost

        elif event.type == EventType.EMBEDDING:
            input_tokens = event.input_tokens or 0
            rate = pricing.embedding_per_1k or pricing.input_per_1k or 0
            if rate > 0 and input_tokens > 0:
                cost = round((input_tokens / 1_000) * rate, 6)
                items.append(
                    CostLineItem(
                        description=f"Embedding tokens: {input_tokens:,} x ${rate}/1K",
                        tokens=input_tokens,
                        rate_per_1k=rate,
                        cost_usd=cost,
                    )
                )
                total += cost

        elif event.type == EventType.IMAGE:
            count = event.metadata.get("image_count", 1)
            if pricing.per_image is not None:
                cost = round(pricing.per_image * count, 6)
                items.append(
                    CostLineItem(
                        description=f"Images: {count} x ${pricing.per_image}",
                        tokens=count,
                        rate_per_1k=pricing.per_image,
                        cost_usd=cost,
                    )
                )
                total += cost

        elif event.type == EventType.AUDIO:
            duration = event.metadata.get("audio_duration_seconds", 0)
            if pricing.per_second_audio is not None:
                cost = round(pricing.per_second_audio * duration, 6)
                items.append(
                    CostLineItem(
                        description=f"Audio: {duration:.1f}s x ${pricing.per_second_audio}/s",
                        tokens=int(duration),
                        rate_per_1k=pricing.per_second_audio,
                        cost_usd=cost,
                    )
                )
                total += cost

        if event.estimated:
            items.append(
                CostLineItem(
                    description="⚠ Token counts are estimated, not actual",
                    cost_usd=0.0,
                )
            )

        return CostExplanation(
            event_id=event.id,
            model=event.model,
            breakdown=items,
            total_usd=round(total, 6),
        )
