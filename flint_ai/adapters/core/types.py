"""Core types for Flint adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
        return ErrorAction.DLQ


@dataclass
class CostBreakdown:
    """Cost breakdown for a single agent run."""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost_usd: float = 0.0
    completion_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    tool_call_costs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt_cost_usd": self.prompt_cost_usd,
            "completion_cost_usd": self.completion_cost_usd,
            "total_cost_usd": self.total_cost_usd,
            "tool_call_costs": self.tool_call_costs,
        }


@dataclass
class ToolExecution:
    """Records a single tool call execution (adapter-side dataclass)."""

    task_id: str = ""
    workflow_run_id: str | None = None
    node_id: str | None = None
    tool_name: str = ""
    input_json: dict[str, Any] | None = None
    output_json: str | dict[str, Any] | None = None
    duration_ms: float | None = None
    error: str | None = None
    stack_trace: str | None = None
    sanitized_input: dict[str, Any] | None = None
    cost_usd: float = 0.0
    status: str = "succeeded"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "workflow_run_id": self.workflow_run_id,
            "node_id": self.node_id,
            "tool_name": self.tool_name,
            "input_json": self.input_json,
            "output_json": self.output_json,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "stack_trace": self.stack_trace,
            "sanitized_input": self.sanitized_input,
            "cost_usd": self.cost_usd,
            "status": self.status,
        }


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
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    cost: CostBreakdown | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"output": self.output, "success": self.success}
        if self.error:
            d["error"] = self.error
        if self.metadata:
            d["metadata"] = self.metadata
        if self.cost:
            d["cost"] = self.cost.to_dict()
        return d


@dataclass
class RegisteredAgent:
    """An agent registered with Flint."""

    name: str
    url: str | None = None
    inline: bool = False
    adapter_type: str = "custom"

    def to_registration_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name}
        if self.url:
            payload["url"] = self.url
        return payload
