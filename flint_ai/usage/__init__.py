"""Unified AI usage and cost tracking for Flint.

This module provides a provider-agnostic system for tracking AI usage
and costs across multiple providers, models, and event types.

Pipeline:
    Adapter → Normalizer → CostEngine → EventEmitter → Aggregator

Quick start:
    from flint_ai.usage import PricingRegistry, CostEngine, EventEmitter
    from flint_ai.usage.adapters.openai import OpenAIAdapter

    pricing = PricingRegistry()
    engine = CostEngine(pricing)
    emitter = EventEmitter()

    adapter = OpenAIAdapter(api_key="...", pricing=pricing, emitter=emitter)
    result = await adapter.execute_llm("gpt-4o", messages=[...])
"""

from __future__ import annotations

from .aggregator import AgentTrace, Aggregator, ModelSummary, RetryAwareCost
from .cost_engine import CostEngine, CostExplanation, CostLineItem
from .events import AIEvent, EventEmitter, EventType
from .normalizer import Normalizer
from .observability import ObservabilityHooks
from .pricing import ModelPricing, PricingRegistry

__all__ = [
    "AIEvent",
    "AgentTrace",
    "Aggregator",
    "CostEngine",
    "CostExplanation",
    "CostLineItem",
    "EventEmitter",
    "EventType",
    "ModelPricing",
    "ModelSummary",
    "Normalizer",
    "ObservabilityHooks",
    "PricingRegistry",
    "RetryAwareCost",
]
