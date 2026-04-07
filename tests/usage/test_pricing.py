"""Tests for PricingRegistry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flint_ai.usage.pricing import ModelPricing, PricingEntry, PricingRegistry


class TestModelPricing:
    def test_default_values(self) -> None:
        p = ModelPricing()
        assert p.input_per_1k is None
        assert p.output_per_1k is None
        assert p.embedding_per_1k is None
        assert p.per_image is None
        assert p.per_second_audio is None

    def test_with_values(self) -> None:
        p = ModelPricing(input_per_1k=0.0025, output_per_1k=0.01)
        assert p.input_per_1k == 0.0025
        assert p.output_per_1k == 0.01


class TestPricingEntry:
    def test_is_active_now(self) -> None:
        entry = PricingEntry(
            provider="openai",
            model="gpt-4o",
            pricing=ModelPricing(input_per_1k=0.0025),
        )
        assert entry.is_active_at()

    def test_is_active_in_past(self) -> None:
        now = datetime.now(timezone.utc)
        entry = PricingEntry(
            provider="openai",
            model="gpt-4o",
            pricing=ModelPricing(input_per_1k=0.0025),
            effective_from=now - timedelta(days=30),
        )
        assert entry.is_active_at(now)

    def test_is_not_active_yet(self) -> None:
        now = datetime.now(timezone.utc)
        entry = PricingEntry(
            provider="openai",
            model="gpt-4o",
            pricing=ModelPricing(input_per_1k=0.0025),
            effective_from=now + timedelta(days=1),
        )
        assert not entry.is_active_at(now)

    def test_is_expired(self) -> None:
        now = datetime.now(timezone.utc)
        entry = PricingEntry(
            provider="openai",
            model="gpt-4o",
            pricing=ModelPricing(input_per_1k=0.0025),
            effective_from=now - timedelta(days=10),
            effective_to=now - timedelta(days=1),
        )
        assert not entry.is_active_at(now)


class TestPricingRegistry:
    def test_loads_openai_defaults(self) -> None:
        registry = PricingRegistry()
        pricing = registry.get_pricing("openai", "gpt-4o")
        assert pricing is not None
        assert pricing.input_per_1k is not None
        assert pricing.output_per_1k is not None

    def test_get_pricing_unknown_model(self) -> None:
        registry = PricingRegistry()
        pricing = registry.get_pricing("openai", "unknown-model-xyz")
        assert pricing is None

    def test_register_custom_pricing(self) -> None:
        registry = PricingRegistry()
        registry.register(
            provider="anthropic",
            model="claude-3-sonnet",
            pricing=ModelPricing(input_per_1k=0.008, output_per_1k=0.024),
        )
        pricing = registry.get_pricing("anthropic", "claude-3-sonnet")
        assert pricing is not None
        assert pricing.input_per_1k == 0.008
        assert pricing.output_per_1k == 0.024

    def test_time_bound_pricing(self) -> None:
        registry = PricingRegistry()
        now = datetime.now(timezone.utc)
        registry.register(
            provider="openai",
            model="gpt-4o",
            pricing=ModelPricing(input_per_1k=0.005),
            effective_from=now - timedelta(days=10),
            effective_to=now - timedelta(days=1),
        )
        pricing = registry.get_pricing("openai", "gpt-4o", when=now)
        assert pricing is not None
        assert pricing.input_per_1k == 0.0025

    def test_list_models(self) -> None:
        registry = PricingRegistry()
        models = registry.list_models("openai")
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models

    def test_list_providers(self) -> None:
        registry = PricingRegistry()
        providers = registry.list_providers()
        assert "openai" in providers

    def test_to_dict(self) -> None:
        registry = PricingRegistry()
        d = registry.to_dict()
        assert "openai" in d
        assert "gpt-4o" in d["openai"]
