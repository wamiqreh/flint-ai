"""Cost tracking for Flint adapters — model-wise pricing and calculation."""

from __future__ import annotations

import logging
import warnings
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

    Pricing is sourced from the centralized CostConfigManager (DB or defaults).
    Supports runtime overrides via cost_config_override parameter.

    For time-bound pricing, use add_time_bound_price() to register prices
    with effective_from/effective_to windows. The calculate() method will
    use the price that was active at the given timestamp.

    Supports text, vision, embedding, and image generation costs.
    """

    # Backward compat: keep reference to defaults for migration
    DEFAULT_PRICING: ClassVar[dict[str, dict[str, float]]] = {}

    def __init__(
        self,
        model: str | None = None,
        provider: str | None = None,
        pricing: dict[str, dict[str, float]] | None = None,
        cost_tracker: FlintCostTracker | None = None,  # deprecated: old API
    ):
        self._model: str | None = None
        self._provider: str | None = None
        self._pricing_cache: dict[str, dict[str, float]] | None = None
        self._time_bound_prices: list[TimeBoundPrice] = []

        # Handle deprecated cost_tracker parameter
        if cost_tracker is not None:
            warnings.warn(
                "Passing cost_tracker= to FlintCostTracker is deprecated. "
                "Use model= and provider= instead, or rely on CostConfigManager.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Copy state from old tracker
            self._pricing_cache = dict(getattr(cost_tracker, "_pricing_cache", getattr(cost_tracker, "_pricing", {})))
            self._time_bound_prices = list(cost_tracker._time_bound_prices)
            return

        self._model = model
        self._provider = provider

        # If custom pricing dict provided, use it directly (backward compat)
        if pricing is not None:
            warnings.warn(
                "Passing pricing= dict to FlintCostTracker is deprecated. "
                "Use CostConfigManager.set_pricing() for runtime overrides.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._pricing_cache = pricing
        else:
            self._pricing_cache = None  # Will fetch from CostConfigManager on demand

    def _get_pricing_for_time(self, model: str, when: datetime | None = None) -> dict[str, float] | None:
        """Get pricing for a model at a given time.

        Checks time-bound prices first, then falls back to CostConfigManager.
        """
        # Check time-bound prices first
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

        # If we have a pricing cache (deprecated pricing= param), use it
        if self._pricing_cache is not None:
            return self._pricing_cache.get(model)

        # Fetch from CostConfigManager
        from flint_ai.config.cost_config import CostConfigManager

        mgr = CostConfigManager.get_instance()
        return mgr.get_pricing(model, self._provider, when)

    def calculate(
        self,
        model: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        executed_at: datetime | None = None,
    ) -> CostBreakdown:
        model = model or self._model or "unknown"
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
        from flint_ai.config.cost_config import CostConfigManager

        return CostConfigManager.get_instance().get_pricing(model, self._provider)

    def list_models(self) -> list[str]:
        from flint_ai.config.cost_config import CostConfigManager

        return CostConfigManager.get_instance().list_models()
