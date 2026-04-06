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
    """A price entry with validity window."""

    model: str
    prompt_cost_per_million: float
    completion_cost_per_million: float
    effective_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    effective_to: datetime | None = None
    provider: str = "openai"

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

    Uses hardcoded default pricing for OpenAI models as fallback.
    Prices are per 1M tokens in USD.

    For time-bound pricing, use add_time_bound_price() to register prices
    with effective_from/effective_to windows. The calculate() method will
    use the price that was active at the given timestamp.
    """

    DEFAULT_PRICING: ClassVar[dict[str, dict[str, float]]] = {
        "gpt-4o": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-2024-05-13": {"prompt": 5.00, "completion": 15.00},
        "gpt-4o-2024-08-06": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-2024-11-20": {"prompt": 2.50, "completion": 10.00},
        "gpt-4o-mini": {"prompt": 0.150, "completion": 0.600},
        "gpt-4o-mini-2024-07-18": {"prompt": 0.150, "completion": 0.600},
        "gpt-4-turbo": {"prompt": 10.00, "completion": 30.00},
        "gpt-4-turbo-2024-04-09": {"prompt": 10.00, "completion": 30.00},
        "gpt-4": {"prompt": 30.00, "completion": 60.00},
        "gpt-4-32k": {"prompt": 60.00, "completion": 120.00},
        "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
        "gpt-3.5-turbo-0125": {"prompt": 0.50, "completion": 1.50},
        "gpt-3.5-turbo-1106": {"prompt": 1.00, "completion": 2.00},
        "gpt-3.5-turbo-instruct": {"prompt": 1.50, "completion": 2.00},
        "o1": {"prompt": 15.00, "completion": 60.00},
        "o1-2024-12-17": {"prompt": 15.00, "completion": 60.00},
        "o1-mini": {"prompt": 3.00, "completion": 12.00},
        "o1-mini-2024-09-12": {"prompt": 3.00, "completion": 12.00},
        "o3-mini": {"prompt": 1.10, "completion": 4.40},
        "o3-mini-2025-01-31": {"prompt": 1.10, "completion": 4.40},
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
                return {
                    "prompt": tbp.prompt_cost_per_million,
                    "completion": tbp.completion_cost_per_million,
                }
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
