"""Centralized cost configuration — pricing from DB with runtime overrides."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("flint.config.cost")


# Default pricing (per 1M tokens, USD) — single source of truth
# Kept here as fallback when DB is unavailable
_DEFAULT_PRICING: dict[str, dict[str, float]] = {
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
    # OpenAI Images / Audio
    "dall-e-3": {"image_generation": 0.04},
    "dall-e-2": {"image_generation": 0.02},
    "whisper-1": {"audio_per_second": 0.006},
    # Anthropic Claude
    "claude-3-5-sonnet-20241022": {"prompt": 3.00, "completion": 15.00},
    "claude-3-opus-20250219": {"prompt": 5.00, "completion": 25.00},
    "claude-3-sonnet-20240229": {"prompt": 3.00, "completion": 15.00},
    "claude-3-haiku-20240307": {"prompt": 0.80, "completion": 4.00},
    "claude-2": {"prompt": 8.00, "completion": 24.00},
    "claude-2.1": {"prompt": 8.00, "completion": 24.00},
}


class _ModelPricing:
    """Internal pricing entry with optional time window."""

    __slots__ = (
        "audio_per_second",
        "completion",
        "effective_from",
        "effective_to",
        "embedding",
        "image_generation",
        "model",
        "prompt",
        "provider",
        "vision",
    )

    def __init__(
        self,
        model: str,
        provider: str,
        prompt: float = 0,
        completion: float = 0,
        vision: float = 0,
        embedding: float = 0,
        image_generation: float = 0,
        audio_per_second: float = 0,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ):
        self.model = model
        self.provider = provider
        self.prompt = prompt
        self.completion = completion
        self.vision = vision
        self.embedding = embedding
        self.image_generation = image_generation
        self.audio_per_second = audio_per_second
        self.effective_from = effective_from or datetime.now(timezone.utc)
        self.effective_to = effective_to

    def is_active_at(self, when: datetime | None = None) -> bool:
        if when is None:
            when = datetime.now(timezone.utc)
        if when < self.effective_from:
            return False
        if self.effective_to is not None and when > self.effective_to:
            return False
        return True

    def to_dict(self) -> dict[str, float]:
        result: dict[str, float] = {}
        if self.prompt:
            result["prompt"] = self.prompt
        if self.completion:
            result["completion"] = self.completion
        if self.vision:
            result["vision"] = self.vision
        if self.embedding:
            result["embedding"] = self.embedding
        if self.image_generation:
            result["image_generation"] = self.image_generation
        if self.audio_per_second:
            result["audio_per_second"] = self.audio_per_second
        return result


class CostConfigManager:
    """Centralized pricing configuration.

    Loads pricing from PostgreSQL flint_model_pricing table on init.
    Falls back to hardcoded defaults if DB is unavailable.
    Supports runtime overrides via set_pricing().

    Singleton — use CostConfigManager.get_instance() to access.

    Usage:
        mgr = CostConfigManager.get_instance()
        pricing = mgr.get_pricing("gpt-4o")
        mgr.set_pricing("gpt-4o", {"prompt": 3.0, "completion": 12.0})
    """

    _instance: CostConfigManager | None = None
    _lock = threading.Lock()

    def __init__(self, db_url: str | None = None) -> None:
        self._pricing: list[_ModelPricing] = []
        self._overrides: dict[str, dict[str, float]] = {}
        self._loaded = False
        self._db_url = db_url or os.environ.get("POSTGRES_URL", os.environ.get("DATABASE_URL"))

    @classmethod
    def get_instance(cls) -> CostConfigManager:
        """Get the singleton CostConfigManager instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._load()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def _load(self) -> None:
        """Load pricing from DB or fallback to defaults."""
        if self._loaded:
            return

        # Try loading from PostgreSQL
        if self._db_url:
            try:
                self._load_from_db()
                self._loaded = True
                logger.info("Loaded pricing from PostgreSQL (%d entries)", len(self._pricing))
                return
            except Exception as e:
                logger.warning("Could not load pricing from DB: %s, using defaults", e)

        # Fallback to defaults
        self._load_from_defaults()
        self._loaded = True
        logger.info("Loaded pricing from defaults (%d entries)", len(self._pricing))

    def _load_from_db(self) -> None:
        """Load pricing from flint_model_pricing table."""
        import asyncpg  # type: ignore

        async def _fetch():
            conn = await asyncpg.connect(self._db_url)
            try:
                rows = await conn.fetch(
                    "SELECT model, provider, prompt_cost_per_million, completion_cost_per_million, "
                    "effective_from, effective_to FROM flint_model_pricing "
                    "WHERE effective_to IS NULL OR effective_to > NOW() "
                    "ORDER BY model, effective_from DESC"
                )
                for row in rows:
                    entry = _ModelPricing(
                        model=row["model"],
                        provider=row["provider"],
                        prompt=float(row["prompt_cost_per_million"]),
                        completion=float(row["completion_cost_per_million"]),
                        effective_from=row["effective_from"],
                        effective_to=row["effective_to"],
                    )
                    self._pricing.append(entry)
            finally:
                await conn.close()

        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context — this shouldn't happen during
                # normal init (sync), but handle gracefully.
                logger.warning("Async event loop running; DB load deferred to first sync call")
                return
            loop.run_until_complete(_fetch())
        except RuntimeError:
            asyncio.run(_fetch())

    def _load_from_defaults(self) -> None:
        """Load pricing from hardcoded defaults."""
        now = datetime.now(timezone.utc)
        for model, prices in _DEFAULT_PRICING.items():
            provider = "anthropic" if model.startswith("claude") else "openai"
            entry = _ModelPricing(
                model=model,
                provider=provider,
                prompt=prices.get("prompt", 0),
                completion=prices.get("completion", 0),
                vision=prices.get("vision", 0),
                embedding=prices.get("embedding", 0),
                image_generation=prices.get("image_generation", 0),
                audio_per_second=prices.get("audio_per_second", 0),
                effective_from=now,
            )
            self._pricing.append(entry)

    def get_pricing(
        self, model: str, provider: str | None = None, when: datetime | None = None
    ) -> dict[str, float] | None:
        """Get active pricing for a model at a given time.

        Checks runtime overrides first, then DB-loaded pricing, then defaults.

        Args:
            model: Model identifier (e.g., "gpt-4o").
            provider: Provider namespace (e.g., "openai", "anthropic"). If None,
                      searches all providers.
            when: Point in time to check (default: now).

        Returns:
            Dict with pricing keys (e.g., {"prompt": 2.50, "completion": 10.00})
            or None if model not found.
        """
        # Check runtime overrides first
        if model in self._overrides:
            return self._overrides[model]

        # Search loaded pricing entries
        matches = [
            p
            for p in self._pricing
            if p.model == model and (provider is None or p.provider == provider) and p.is_active_at(when)
        ]

        if not matches:
            # Last resort: check defaults directly
            return _DEFAULT_PRICING.get(model)

        # Return the most recent match
        return matches[-1].to_dict()

    def set_pricing(self, model: str, pricing: dict[str, float], provider: str = "custom") -> None:
        """Set a runtime pricing override for a model.

        This does NOT persist to the database. It overrides in-memory only.

        Args:
            model: Model identifier.
            pricing: Pricing dict (e.g., {"prompt": 3.0, "completion": 12.0}).
            provider: Provider namespace (default: "custom").
        """
        self._overrides[model] = pricing
        logger.debug("Set runtime pricing override for %s: %s", model, pricing)

    def remove_override(self, model: str) -> None:
        """Remove a runtime pricing override."""
        self._overrides.pop(model, None)

    def list_models(self) -> list[str]:
        """List all known models (from DB + defaults)."""
        models = set(_DEFAULT_PRICING.keys())
        for p in self._pricing:
            models.add(p.model)
        return sorted(models)

    def list_providers(self) -> list[str]:
        """List all known providers."""
        providers = {"openai", "anthropic"}
        for p in self._pricing:
            providers.add(p.provider)
        return sorted(providers)

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Export all pricing as dict: {model: pricing_dict}."""
        result: dict[str, dict[str, Any]] = {}
        for p in self._pricing:
            if p.model not in result:
                result[p.model] = p.to_dict()
        # Include overrides
        for model, pricing in self._overrides.items():
            result[model] = pricing
        return result


# Convenience function for quick access
def get_pricing(model: str, provider: str | None = None) -> dict[str, float] | None:
    """Get pricing for a model from the centralized config manager."""
    return CostConfigManager.get_instance().get_pricing(model, provider)


def set_pricing(model: str, pricing: dict[str, float]) -> None:
    """Set a runtime pricing override."""
    CostConfigManager.get_instance().set_pricing(model, pricing)
