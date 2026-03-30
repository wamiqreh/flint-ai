"""Flint adapters — plug any AI agent framework into Flint.

Usage:
    from flint_ai.adapters.openai import FlintOpenAIAgent
    from flint_ai.adapters.crewai import FlintCrewAIAdapter
    from flint_ai.adapters.langgraph import FlintLangGraphAdapter
    from flint_ai.adapters.core import FlintAdapter, AdapterConfig
"""

from .core import (
    AdapterConfig,
    AgentRunResult,
    ErrorAction,
    ErrorMapping,
    FlintAdapter,
    RegisteredAgent,
    start_worker,
    stop_worker,
)
from .langgraph import FlintLangGraphAdapter

__all__ = [
    "FlintAdapter",
    "AdapterConfig",
    "AgentRunResult",
    "ErrorAction",
    "ErrorMapping",
    "RegisteredAgent",
    "start_worker",
    "stop_worker",
    "FlintLangGraphAdapter",
]
