"""Flint adapters — plug any AI agent framework into Flint.

Usage:
    from flint_ai.adapters.openai import FlintOpenAIAgent
    from flint_ai.adapters.anthropic import FlintAnthropicAgent
    from flint_ai.adapters.crewai import FlintCrewAIAdapter
    from flint_ai.adapters.core import FlintAdapter, AdapterConfig
"""

from .core import (
    AdapterConfig,
    AgentRunResult,
    CostBreakdown,
    ErrorAction,
    ErrorMapping,
    FlintAdapter,
    FlintCostTracker,
    RegisteredAgent,
    start_worker,
    stop_worker,
)

__all__ = [
    "AdapterConfig",
    "AgentRunResult",
    "CostBreakdown",
    "ErrorAction",
    "ErrorMapping",
    "FlintAdapter",
    "FlintCostTracker",
    "RegisteredAgent",
    "start_worker",
    "stop_worker",
]
