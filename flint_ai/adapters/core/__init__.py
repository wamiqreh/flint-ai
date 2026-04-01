"""Flint adapter core — base classes, registry, and inline worker."""

from .base import FlintAdapter
from .registry import (
    auto_register,
    get_inline_adapter,
    list_inline_adapters,
    register_inline,
    register_with_flint,
)
from .types import AdapterConfig, AgentRunResult, ErrorAction, ErrorMapping, RegisteredAgent
from .worker import InlineWorker, start_worker, stop_worker

__all__ = [
    "FlintAdapter",
    "AdapterConfig",
    "AgentRunResult",
    "ErrorAction",
    "ErrorMapping",
    "RegisteredAgent",
    "InlineWorker",
    "auto_register",
    "get_inline_adapter",
    "list_inline_adapters",
    "register_inline",
    "register_with_flint",
    "start_worker",
    "stop_worker",
]
