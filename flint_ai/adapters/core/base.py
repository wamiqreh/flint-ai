"""Base adapter class for Flint agent adapters."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from .types import AdapterConfig, AgentRunResult, ErrorAction, ErrorMapping, RegisteredAgent

logger = logging.getLogger("flint.adapters")

# OTel tracing — optional, no-op if not installed
try:
    from opentelemetry import trace

    _tracer = trace.get_tracer("flint.adapters")
except ImportError:
    _tracer = None


class FlintAdapter(ABC):
    """Abstract base class for all Flint agent adapters.

    Subclass this to create an adapter for any AI agent framework.
    The adapter wraps your agent's execution logic and integrates it
    with Flint's queue, retry, DAG, and approval systems.

    Example:
        class MyAgent(FlintAdapter):
            def __init__(self, name: str):
                super().__init__(name=name)

            async def run(self, input_data: dict) -> AgentRunResult:
                result = await my_framework.execute(input_data["prompt"])
                return AgentRunResult(output=result)
    """

    def __init__(
        self,
        *,
        name: str,
        config: Optional[AdapterConfig] = None,
        error_mapping: Optional[ErrorMapping] = None,
    ):
        self._name = name
        self._config = config or AdapterConfig()
        self._error_mapping = error_mapping or ErrorMapping()
        self._registered = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> AdapterConfig:
        return self._config

    @property
    def error_mapping(self) -> ErrorMapping:
        return self._error_mapping

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> AgentRunResult:
        """Execute the agent with the given input.

        Args:
            input_data: Dict with at least {"prompt": "..."}.
                        May also contain task_id, workflow_id, metadata.

        Returns:
            AgentRunResult with output text and success status.
        """
        ...

    def get_agent_name(self) -> str:
        """Return the agent name used for Flint registration."""
        return self._name

    def to_registered_agent(self) -> RegisteredAgent:
        """Convert this adapter to a RegisteredAgent for Flint."""
        return RegisteredAgent(
            name=self._name,
            inline=self._config.inline,
            adapter_type=self.__class__.__name__,
        )

    async def safe_run(self, input_data: dict[str, Any]) -> AgentRunResult:
        """Run the agent with error classification and optional OTel tracing.

        Catches exceptions, classifies them via error_mapping,
        and returns an AgentRunResult with appropriate error info.
        Automatically creates OpenTelemetry spans if the SDK is installed.
        """
        start = time.monotonic()

        # Create OTel span if tracing is available
        if _tracer is not None:
            with _tracer.start_as_current_span(
                f"flint.adapter.{self._name}",
                attributes={
                    "flint.adapter.name": self._name,
                    "flint.adapter.type": self.__class__.__name__,
                    "flint.prompt.length": len(input_data.get("prompt", "")),
                },
            ) as span:
                try:
                    result = await self.run(input_data)
                    span.set_attribute("flint.adapter.success", True)
                    span.set_attribute("flint.adapter.duration_ms", (time.monotonic() - start) * 1000)
                    return result
                except Exception as exc:
                    action = self._error_mapping.classify(exc)
                    span.set_attribute("flint.adapter.success", False)
                    span.set_attribute("flint.adapter.error_action", action.value)
                    span.set_attribute("flint.adapter.error", str(exc))
                    span.record_exception(exc)
                    logger.warning("Agent %s failed (action=%s): %s", self._name, action.value, exc)
                    return AgentRunResult(
                        output="",
                        success=False,
                        error=str(exc),
                        metadata={"error_action": action.value, "error_type": type(exc).__name__},
                    )

        # No OTel — run without tracing
        try:
            return await self.run(input_data)
        except Exception as exc:
            action = self._error_mapping.classify(exc)
            logger.warning("Agent %s failed (action=%s): %s", self._name, action.value, exc)
            return AgentRunResult(
                output="",
                success=False,
                error=str(exc),
                metadata={"error_action": action.value, "error_type": type(exc).__name__},
            )
