"""Flint OpenAI Adapter — use OpenAI models as Flint agents."""

from .agent import FlintOpenAIAgent
from .tools import tool, get_tool_schemas, execute_tool_call

__all__ = [
    "FlintOpenAIAgent",
    "tool",
    "get_tool_schemas",
    "execute_tool_call",
]
