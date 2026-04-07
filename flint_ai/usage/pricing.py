"""Centralized pricing registry for AI models."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("flint.usage.pricing")


class ModelPricing(BaseModel):
    """Pricing configuration for a specific AI model.

    All prices are in USD. Token-based prices are per 1K tokens.
    """

    input_per_1k: float | None = None
    output_per_1k: float | None = None
    embedding_per_1k: float | None = None
    per_image: float | None = None
    per_second_audio: float | None = None
    cache_read_per_1k: float | None = None
    cache_write_per_1k: float | None = None


class PricingEntry(BaseModel):
    """A pricing entry with an optional validity window."""

    provider: str
    model: str
    pricing: ModelPricing
    effective_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_to: datetime | None = None

    def is_active_at(self, when: datetime | None = None) -> bool:
        if when is None:
            when = datetime.now(timezone.utc)
        if when < self.effective_from:
            return False
        if self.effective_to is not None and when > self.effective_to:
            return False
        return True


_OPENAI_DEFAULTS: dict[str, dict[str, float]] = {
    "gpt-4o": {"input_per_1k": 0.00250, "output_per_1k": 0.01000},
    "gpt-4o-2024-05-13": {"input_per_1k": 0.00500, "output_per_1k": 0.01500},
    "gpt-4o-2024-08-06": {"input_per_1k": 0.00250, "output_per_1k": 0.01000},
    "gpt-4o-2024-11-20": {"input_per_1k": 0.00250, "output_per_1k": 0.01000},
    "gpt-4o-mini": {"input_per_1k": 0.000150, "output_per_1k": 0.000600},
    "gpt-4o-mini-2024-07-18": {"input_per_1k": 0.000150, "output_per_1k": 0.000600},
    "gpt-4-turbo": {"input_per_1k": 0.01000, "output_per_1k": 0.03000},
    "gpt-4-turbo-2024-04-09": {"input_per_1k": 0.01000, "output_per_1k": 0.03000},
    "gpt-4": {"input_per_1k": 0.03000, "output_per_1k": 0.06000},
    "gpt-4-32k": {"input_per_1k": 0.06000, "output_per_1k": 0.12000},
    "gpt-3.5-turbo": {"input_per_1k": 0.00050, "output_per_1k": 0.00150},
    "gpt-3.5-turbo-0125": {"input_per_1k": 0.00050, "output_per_1k": 0.00150},
    "gpt-3.5-turbo-1106": {"input_per_1k": 0.00100, "output_per_1k": 0.00200},
    "gpt-3.5-turbo-instruct": {"input_per_1k": 0.00150, "output_per_1k": 0.00200},
    "o1": {"input_per_1k": 0.01500, "output_per_1k": 0.06000},
    "o1-2024-12-17": {"input_per_1k": 0.01500, "output_per_1k": 0.06000},
    "o1-mini": {"input_per_1k": 0.00300, "output_per_1k": 0.01200},
    "o1-mini-2024-09-12": {"input_per_1k": 0.00300, "output_per_1k": 0.01200},
    "o3-mini": {"input_per_1k": 0.00110, "output_per_1k": 0.00440},
    "o3-mini-2025-01-31": {"input_per_1k": 0.00110, "output_per_1k": 0.00440},
    "text-embedding-3-small": {"embedding_per_1k": 0.00002},
    "text-embedding-3-large": {"embedding_per_1k": 0.00013},
    "text-embedding-ada-002": {"embedding_per_1k": 0.00010},
    "dall-e-3": {"per_image": 0.04},
    "dall-e-2": {"per_image": 0.02},
    "whisper-1": {"per_second_audio": 0.006},
    "gpt-4o-realtime": {"input_per_1k": 0.00500, "output_per_1k": 0.02000, "per_second_audio": 0.0001},
    "gpt-4o-audio-preview": {"input_per_1k": 0.00250, "output_per_1k": 0.01000, "per_second_audio": 0.00004},
    "gpt-4o-mini-realtime": {"input_per_1k": 0.00060, "output_per_1k": 0.00240, "per_second_audio": 0.00004},
}


class PricingRegistry:
    """Centralized, provider-agnostic pricing registry.

    Decouples pricing from adapters. Supports time-bound pricing
    and per-provider model namespaces.

    Usage:
        registry = PricingRegistry()
        pricing = registry.get_pricing("openai", "gpt-4o")
    """

    def __init__(self) -> None:
        self._entries: list[PricingEntry] = []
        self._load_defaults()

    def _load_defaults(self) -> None:
        now = datetime.now(timezone.utc)
        for model, prices in _OPENAI_DEFAULTS.items():
            pricing = ModelPricing(**prices)
            entry = PricingEntry(
                provider="openai",
                model=model,
                pricing=pricing,
                effective_from=now,
            )
            self._entries.append(entry)

    def register(
        self,
        provider: str,
        model: str,
        pricing: ModelPricing,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> None:
        """Register pricing for a model.

        Args:
            provider: Provider namespace (e.g., "openai", "anthropic").
            model: Model identifier (e.g., "gpt-4o").
            pricing: Pricing configuration.
            effective_from: When this pricing becomes active (default: now).
            effective_to: When this pricing expires (default: never).
        """
        entry = PricingEntry(
            provider=provider,
            model=model,
            pricing=pricing,
            effective_from=effective_from or datetime.now(timezone.utc),
            effective_to=effective_to,
        )
        self._entries.append(entry)
        logger.debug("Registered pricing for %s:%s", provider, model)

    def get_pricing(
        self,
        provider: str,
        model: str,
        when: datetime | None = None,
    ) -> ModelPricing | None:
        """Get pricing for a model at a given time.

        Returns the most recently registered pricing entry that was active
        at the given time. If no time-bound entry matches, returns None.

        Args:
            provider: Provider namespace.
            model: Model identifier.
            when: Point in time to check (default: now).

        Returns:
            ModelPricing if found, None otherwise.
        """
        if when is None:
            when = datetime.now(timezone.utc)

        matching = [e for e in self._entries if e.provider == provider and e.model == model and e.is_active_at(when)]

        if not matching:
            return None

        return matching[-1].pricing

    def list_models(self, provider: str | None = None) -> list[str]:
        """List all registered models, optionally filtered by provider."""
        models = set()
        for entry in self._entries:
            if provider is None or entry.provider == provider:
                models.add(entry.model)
        return sorted(models)

    def list_providers(self) -> list[str]:
        """List all registered providers."""
        return sorted({e.provider for e in self._entries})

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Export all pricing as a nested dict: {provider: {model: pricing_dict}}."""
        result: dict[str, dict[str, Any]] = {}
        for entry in self._entries:
            if entry.provider not in result:
                result[entry.provider] = {}
            result[entry.provider][entry.model] = entry.pricing.model_dump()
        return result
