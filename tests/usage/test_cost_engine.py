"""Tests for CostEngine."""

from __future__ import annotations

import pytest

from flint_ai.usage.cost_engine import CostEngine, CostExplanation
from flint_ai.usage.events import AIEvent, EventType
from flint_ai.usage.pricing import ModelPricing, PricingRegistry


class TestCostEngine:
    @pytest.fixture
    def registry(self) -> PricingRegistry:
        return PricingRegistry()

    @pytest.fixture
    def engine(self, registry: PricingRegistry) -> CostEngine:
        return CostEngine(registry)

    def test_calculate_llm(self, engine: CostEngine) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=1000,
            output_tokens=500,
        )
        cost = engine.calculate(event)
        assert cost > 0

    def test_calculate_llm_with_cache(self, engine: CostEngine) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=1000,
            output_tokens=500,
            metadata={"cached_tokens": 200},
        )
        cost = engine.calculate(event)
        assert cost >= 0

    def test_calculate_embedding(self, registry: PricingRegistry) -> None:
        registry.register(
            provider="openai",
            model="text-embedding-3-small",
            pricing=ModelPricing(embedding_per_1k=0.00002),
        )
        engine = CostEngine(registry)
        event = AIEvent(
            provider="openai",
            model="text-embedding-3-small",
            type=EventType.EMBEDDING,
            input_tokens=1000,
        )
        cost = engine.calculate(event)
        assert cost == pytest.approx(0.00002, rel=1e-6)

    def test_calculate_image(self, registry: PricingRegistry) -> None:
        engine = CostEngine(registry)
        event = AIEvent(
            provider="openai",
            model="dall-e-3",
            type=EventType.IMAGE,
            metadata={"image_count": 2},
        )
        cost = engine.calculate(event)
        assert cost > 0

    def test_calculate_audio(self, registry: PricingRegistry) -> None:
        engine = CostEngine(registry)
        event = AIEvent(
            provider="openai",
            model="whisper-1",
            type=EventType.AUDIO,
            metadata={"audio_duration_seconds": 30.0},
        )
        cost = engine.calculate(event)
        assert cost > 0

    def test_no_pricing_returns_zero(self, engine: CostEngine) -> None:
        event = AIEvent(
            provider="unknown",
            model="unknown-model",
            type=EventType.LLM_CALL,
            input_tokens=100,
            output_tokens=50,
        )
        cost = engine.calculate(event)
        assert cost == 0.0

    def test_explain_cost_llm(self, engine: CostEngine) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=1000,
            output_tokens=500,
        )
        explanation = engine.explain_cost(event)
        assert isinstance(explanation, CostExplanation)
        assert explanation.event_id == event.id
        assert explanation.model == "gpt-4o"
        assert len(explanation.breakdown) >= 2
        assert explanation.total_usd > 0

    def test_explain_cost_summary_format(self, engine: CostEngine) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=1000,
            output_tokens=500,
        )
        explanation = engine.explain_cost(event)
        summary = explanation.summary()
        assert "gpt-4o" in summary
        assert "Total:" in summary

    def test_explain_cost_no_pricing(self, engine: CostEngine) -> None:
        event = AIEvent(
            provider="unknown",
            model="unknown",
            type=EventType.LLM_CALL,
            input_tokens=100,
        )
        explanation = engine.explain_cost(event)
        assert len(explanation.breakdown) == 1
        assert explanation.total_usd == 0.0

    def test_cost_is_rounded(self, engine: CostEngine) -> None:
        event = AIEvent(
            provider="openai",
            model="gpt-4o",
            type=EventType.LLM_CALL,
            input_tokens=1,
            output_tokens=1,
        )
        cost = engine.calculate(event)
        assert cost == round(cost, 6)
