"""Core types for Flint adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ErrorAction(str, Enum):
    """What Flint should do when an agent error occurs."""

    RETRY = "retry"
    FAIL = "fail"
    DLQ = "dlq"


@dataclass
class ErrorMapping:
    """Maps exception types to Flint error actions.

    Example:
        ErrorMapping(
            retry_on=[RateLimitError, TimeoutError],
            fail_on=[InvalidRequestError],
        )
    """

    retry_on: list[type[Exception]] = field(default_factory=list)
    fail_on: list[type[Exception]] = field(default_factory=list)

    def classify(self, exc: Exception) -> ErrorAction:
        for cls in self.retry_on:
            if isinstance(exc, cls):
                return ErrorAction.RETRY
        for cls in self.fail_on:
            if isinstance(exc, cls):
                return ErrorAction.FAIL
        # Unknown errors go to DLQ by default
        return ErrorAction.DLQ


@dataclass
class AdapterConfig:
    """Configuration for a Flint adapter."""

    flint_url: str = "http://localhost:5156"
    inline: bool = True
    auto_register: bool = True
    timeout_seconds: float = 300.0
    max_retries: int = 3
    dead_letter_on_failure: bool = True
    human_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunResult:
    """Result from running an agent."""

    output: str
    success: bool = True
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"output": self.output, "success": self.success}
        if self.error:
            d["error"] = self.error
        if self.metadata:
            d["metadata"] = self.metadata
        return d


@dataclass
class RegisteredAgent:
    """An agent registered with Flint."""

    name: str
    url: Optional[str] = None
    inline: bool = False
    adapter_type: str = "custom"

    def to_registration_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name}
        if self.url:
            payload["url"] = self.url
        return payload
