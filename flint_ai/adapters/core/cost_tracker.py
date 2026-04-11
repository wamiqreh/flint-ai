"""Cost tracking for Flint adapters — model-wise pricing and calculation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

from .types import CostBreakdown

logger = logging.getLogger("flint.adapters.cost")


@dataclass
class TimeBoundPrice:
    """A price entry with validity window.

    Supports text, vision, embedding, and image generation pricing.
    For text models: prompt_cost_per_million, completion_cost_per_million
    For vision: vision_input_cost_per_million (per image token)
    For embeddings: embedding_cost_per_million
    For image generation: image_generation_cost (per image)
    """

    model: str
    prompt_cost_per_million: float
    completion_cost_per_million: float
    effective_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    effective_to: datetime | None = None
    provider: str = "openai"
    vision_input_cost_per_million: float = 0.0
    embedding_cost_per_million: float = 0.0
    image_generation_cost: float = 0.0

    def is_active_at(self, when: datetime | None = None) -> bool:
        if when is None:
            when = datetime.now(timezone.utc)
        if when < self.effective_from:
            return False
        if self.effective_to is not None and when > self.effective_to:
            return False
        return True


class FlintCostTracker:
    """Model-wise pricing and cost calculation.

    Uses hardcoded default pricing for OpenAI, Anthropic, and other models as fallback.
    Prices are per 1M tokens in USD (except image generation which is per image).

    For time-bound pricing, use add_time_bound_price() to register prices
    with effective_from/effective_to windows. The calculate() method will
    use the price that was active at the given timestamp.

    Supports text, vision, embedding, and image generation costs.
    """

    DEFAULT_PRICING: ClassVar[dict[str, dict[str, float]]] = {
        # OpenAI GPT-4o (text + vision)
        "gpt-4o": {"prompt": 2.50, "completion": 10.00, "vision": 2.50},
        "gpt-4o-2024-05-13": {"prompt": 5.00, "completion": 15.00, "vision": 5.00},
        "gpt-4o-2024-08-06": {"prompt": 2.50, "completion": 10.00, "vision": 2.50},
        "gpt-4o-2024-11-20": {"prompt": 2.50, "completion": 10.00, "vision": 2.50},
        "gpt-4o-mini": {"prompt": 0.150, "completion": 0.600, "vision": 0.075},
        "gpt-4o-mini-2024-07-18": {"prompt": 0.150, "completion": 0.600, "vision": 0.075},
        # OpenAI GPT-4 (text)
        "gpt-4-turbo": {"prompt": 10.00, "completion": 30.00},
        "gpt-4-turbo-2024-04-09": {"prompt": 10.00, "completion": 30.00},
        "gpt-4": {"prompt": 30.00, "completion": 60.00},
        "gpt-4-32k": {"prompt": 60.00, "completion": 120.00},
        # OpenAI GPT-3.5 (text)
        "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
        "gpt-3.5-turbo-0125": {"prompt": 0.50, "completion": 1.50},
        "gpt-3.5-turbo-1106": {"prompt": 1.00, "completion": 2.00},
        "gpt-3.5-turbo-instruct": {"prompt": 1.50, "completion": 2.00},
        # OpenAI o1/o3 (reasoning)
        "o1": {"prompt": 15.00, "completion": 60.00},
        "o1-2024-12-17": {"prompt": 15.00, "completion": 60.00},
        "o1-mini": {"prompt": 3.00, "completion": 12.00},
        "o1-mini-2024-09-12": {"prompt": 3.00, "completion": 12.00},
        "o3-mini": {"prompt": 1.10, "completion": 4.40},
        "o3-mini-2025-01-31": {"prompt": 1.10, "completion": 4.40},
        # OpenAI Embeddings
        "text-embedding-3-small": {"embedding": 0.02},
        "text-embedding-3-large": {"embedding": 0.13},
        "text-embedding-ada-002": {"embedding": 0.10},
        # Anthropic Claude 3.5 Sonnet (2026 rates)
        "claude-3-5-sonnet-20241022": {"prompt": 3.00, "completion": 15.00},
        # Anthropic Claude 3 Opus
        "claude-3-opus-20250219": {"prompt": 5.00, "completion": 25.00},
        # Anthropic Claude 3 Sonnet
        "claude-3-sonnet-20240229": {"prompt": 3.00, "completion": 15.00},
        # Anthropic Claude 3 Haiku (most affordable)
        "claude-3-haiku-20240307": {"prompt": 0.80, "completion": 4.00},
        # Anthropic Claude 2
        "claude-2": {"prompt": 8.00, "completion": 24.00},
        "claude-2.1": {"prompt": 8.00, "completion": 24.00},
    }

    def __init__(self, pricing: dict[str, dict[str, float]] | None = None):
        self._pricing: dict[str, dict[str, float]] = {
            **self.DEFAULT_PRICING,
            **(pricing or {}),
        }
        self._time_bound_prices: list[TimeBoundPrice] = []

    def add_time_bound_price(self, price: TimeBoundPrice) -> None:
        """Add a time-bound price entry. Takes precedence over DEFAULT_PRICING."""
        self._time_bound_prices.append(price)

    def _get_pricing_for_time(self, model: str, when: datetime | None = None) -> dict[str, float] | None:
        # First check time-bound prices
        for tbp in self._time_bound_prices:
            if tbp.model == model and tbp.is_active_at(when):
                pricing = {
                    "prompt": tbp.prompt_cost_per_million,
                    "completion": tbp.completion_cost_per_million,
                }
                if tbp.vision_input_cost_per_million > 0:
                    pricing["vision"] = tbp.vision_input_cost_per_million
                if tbp.embedding_cost_per_million > 0:
                    pricing["embedding"] = tbp.embedding_cost_per_million
                if tbp.image_generation_cost > 0:
                    pricing["image_generation"] = tbp.image_generation_cost
                return pricing
        # Fall back to current pricing
        return self._pricing.get(model)

    def calculate(
        self,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        executed_at: datetime | None = None,
    ) -> CostBreakdown:
        pricing = self._get_pricing_for_time(model, executed_at)
        if pricing is None:
            logger.warning("No pricing found for model=%s, returning zero cost", model)
            return CostBreakdown(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )

        effective_prompt = prompt_tokens - cached_tokens
        prompt_cost = (effective_prompt / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

        return CostBreakdown(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            prompt_cost_usd=round(prompt_cost, 6),
            completion_cost_usd=round(completion_cost, 6),
            total_cost_usd=round(prompt_cost + completion_cost, 6),
        )

    def calculate_vision(
        self,
        model: str,
        image_tokens: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        executed_at: datetime | None = None,
    ) -> CostBreakdown:
        """Calculate cost for vision-enabled requests (includes image token pricing)."""
        pricing = self._get_pricing_for_time(model, executed_at)
        if pricing is None:
            logger.warning("No pricing found for model=%s (vision), returning zero cost", model)
            return CostBreakdown(
                model=model,
                prompt_tokens=prompt_tokens + image_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + image_tokens + completion_tokens,
            )

        effective_prompt = prompt_tokens - cached_tokens
        vision_cost_per_million = pricing.get("vision", pricing.get("prompt", 0))

        prompt_cost = (effective_prompt / 1_000_000) * pricing["prompt"]
        image_cost = (image_tokens / 1_000_000) * vision_cost_per_million
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

        total_cost = prompt_cost + image_cost + completion_cost
        return CostBreakdown(
            model=model,
            prompt_tokens=prompt_tokens + image_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + image_tokens + completion_tokens,
            prompt_cost_usd=round(prompt_cost + image_cost, 6),
            completion_cost_usd=round(completion_cost, 6),
            total_cost_usd=round(total_cost, 6),
        )

    def calculate_embedding(
        self,
        model: str,
        input_tokens: int = 0,
        executed_at: datetime | None = None,
    ) -> CostBreakdown:
        """Calculate cost for embedding requests."""
        pricing = self._get_pricing_for_time(model, executed_at)
        if pricing is None or "embedding" not in pricing:
            logger.warning("No embedding pricing found for model=%s, returning zero cost", model)
            return CostBreakdown(
                model=model,
                prompt_tokens=input_tokens,
                total_tokens=input_tokens,
            )

        embedding_cost = (input_tokens / 1_000_000) * pricing["embedding"]
        return CostBreakdown(
            model=model,
            prompt_tokens=input_tokens,
            total_tokens=input_tokens,
            prompt_cost_usd=round(embedding_cost, 6),
            total_cost_usd=round(embedding_cost, 6),
        )

    def add_tool_cost(
        self,
        breakdown: CostBreakdown,
        tool_name: str,
        cost_usd: float,
    ) -> None:
        breakdown.tool_call_costs.append(
            {
                "tool_name": tool_name,
                "cost_usd": round(cost_usd, 6),
            }
        )

    def get_pricing(self, model: str) -> dict[str, float] | None:
        return self._pricing.get(model)

    def list_models(self) -> list[str]:
        return sorted(self._pricing.keys())
