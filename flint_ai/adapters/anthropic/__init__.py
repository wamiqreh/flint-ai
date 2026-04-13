"""Flint Anthropic Adapter — run Claude as Flint workflow tasks.

This adapter wraps the Anthropic Claude API, giving you the natural Anthropic
developer experience with Flint's queue, retry, DAG, and approval infrastructure.

Usage:
    from flint_ai.adapters.anthropic import FlintAnthropicAgent
    from flint_ai import tool

    @tool
    def search_knowledge_base(query: str) -> str:
        return "search results..."

    agent = FlintAnthropicAgent(
        name="researcher",
        model="claude-3-5-sonnet-20241022",
        instructions="You are an expert researcher.",
        tools=[search_knowledge_base],
    )

    # Use in a workflow
    from flint_ai import Workflow, Node
    wf = (Workflow("research-pipeline")
        .add(Node("research", agent=agent, prompt="Research this topic"))
        .build())
"""

from __future__ import annotations

import importlib.util
import logging
import os
import traceback
from typing import Any

from ..core.base import FlintAdapter
from ..core.cost_tracker import FlintCostTracker
from ..core.sanitization import sanitize_input
from ..core.types import AdapterConfig, AgentRunResult, ErrorMapping, ToolExecution

logger = logging.getLogger("flint.adapters.anthropic")

# Anthropic error mapping
_ANTHROPIC_ERROR_MAPPING: ErrorMapping | None = None


def _get_anthropic_error_mapping() -> ErrorMapping:
    """Build error mapping for Anthropic exceptions."""
    global _ANTHROPIC_ERROR_MAPPING
    if _ANTHROPIC_ERROR_MAPPING is not None:
        return _ANTHROPIC_ERROR_MAPPING

    retry_on: list[type[Exception]] = [TimeoutError, ConnectionError]
    fail_on: list[type[Exception]] = [ValueError]

    try:
        from anthropic import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
        )

        retry_on.extend([APITimeoutError, APIConnectionError, AuthenticationError])
        fail_on.extend([BadRequestError, APIStatusError])
    except ImportError:
        pass

    _ANTHROPIC_ERROR_MAPPING = ErrorMapping(retry_on=retry_on, fail_on=fail_on)
    return _ANTHROPIC_ERROR_MAPPING


class FlintAnthropicAgent(FlintAdapter):
    """Wrap a Claude model (with optional tools) as a Flint agent.

    Features:
    - Seamless integration with Flint Workflow/Node DSL
    - Automatic tool calling and schema conversion
    - Cost tracking via FlintCostTracker
    - Error handling and retry logic
    - Request/response sanitization for logging
    """

    def __init__(
        self,
        *,
        name: str,
        model: str,
        instructions: str = "",
        tools: list[Any] | None = None,
        enable_cost_tracking: bool = True,
        cost_config_override: dict[str, float] | None = None,
        config: AdapterConfig | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        # Deprecated — still accepted for backward compat
        cost_tracker: FlintCostTracker | None = None,
    ) -> None:
        """Initialize Claude agent.

        Args:
            name: Agent name (must be unique in workflow).
            model: Claude model ID (e.g., "claude-3-5-sonnet-20241022").
            instructions: System prompt for the agent.
            tools: Optional tool functions decorated with @tool.
            enable_cost_tracking: Enable automatic cost tracking (default: True).
            cost_config_override: Optional pricing override dict for the model.
            config: Adapter configuration (retries, approval, logging).
            temperature: Sampling temperature (0-1).
            max_tokens: Max output tokens.
            cost_tracker: Deprecated — use enable_cost_tracking= instead.
        """
        super().__init__(
            name=name,
            config=config,
            error_mapping=_get_anthropic_error_mapping(),
        )
        self.model = model
        self.instructions = instructions
        self.tools = tools or []
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client: Any = None

        # Cost tracking setup
        if cost_tracker is not None:
            import warnings

            warnings.warn(
                "cost_tracker= is deprecated. Use enable_cost_tracking= and cost_config_override= instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.cost_tracker = cost_tracker
        elif enable_cost_tracking:
            kwargs: dict = {"model": model, "provider": "anthropic"}
            if cost_config_override:
                from flint_ai.config.cost_config import CostConfigManager

                CostConfigManager.get_instance().set_pricing(model, cost_config_override)
            self.cost_tracker = FlintCostTracker(**kwargs)
        else:
            self.cost_tracker = None

    async def run(
        self,
        input_data: dict[str, Any],
    ) -> AgentRunResult:
        """Run the Claude agent on a task.

        Args:
            input_data: Dict with at least {"prompt": "..."}.
                       May also contain task_id, workflow_id, metadata.

        Returns:
            AgentRunResult with output text and success status.
        """
        if importlib.util.find_spec("anthropic") is None:
            return AgentRunResult(
                output="",
                success=False,
                error="anthropic library required: pip install anthropic",
            )

        error_mapping = _get_anthropic_error_mapping()

        # Extract prompt from input_data (required key)
        prompt = input_data.get("prompt", "")
        if not prompt:
            return AgentRunResult(
                output="",
                success=False,
                error="input_data must contain 'prompt' key",
            )

        # Build messages
        system_prompt = self.instructions

        messages = [{"role": "user", "content": prompt}]

        # Sanitize for logging
        sanitized_prompt = sanitize_input(prompt, max_string_length=500)
        logger.debug("[%s] Task: %s", self.name, sanitized_prompt)

        client = self._get_client()

        # Track metrics
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        all_tool_calls: list[dict[str, Any]] = []

        # LLM call loop (handle tool calls)
        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.debug("[%s] Calling Claude (attempt %d)", self.name, attempt)

                response = await client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=messages,
                    temperature=self.temperature,
                    tools=self._get_tool_schemas() if self.tools else None,
                )

                # Track usage
                if response.usage:
                    total_input_tokens += response.usage.input_tokens
                    total_output_tokens += response.usage.output_tokens

                    cost = (
                        self.cost_tracker.calculate(
                            model=self.model,
                            prompt_tokens=response.usage.input_tokens,
                            completion_tokens=response.usage.output_tokens,
                        )
                        if self.cost_tracker
                        else None
                    )
                    if cost:
                        total_cost += cost.total_usd

                # Extract response content
                response_text = ""
                tool_calls = []
                has_tool_use = False

                for block in response.content:
                    if hasattr(block, "text"):
                        response_text += block.text
                    elif block.type == "tool_use":
                        has_tool_use = True
                        tool_calls.append(
                            {
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )

                # If no tool calls, we're done
                if not has_tool_use:
                    logger.debug("[%s] Response: %s", self.name, sanitize_input(response_text))
                    return AgentRunResult(
                        output=response_text,
                        success=True,
                        metadata={
                            "model": self.model,
                            "attempts": attempt,
                            "input_tokens": total_input_tokens,
                            "output_tokens": total_output_tokens,
                        },
                        cost=self.cost_tracker.calculate(
                            model=self.model,
                            prompt_tokens=total_input_tokens,
                            completion_tokens=total_output_tokens,
                        )
                        if self.cost_tracker
                        else None,
                    )

                # Execute tools and add results to messages
                logger.debug("[%s] Executing %d tools", self.name, len(tool_calls))

                # Add assistant message with tool uses
                messages.append({"role": "assistant", "content": response.content})

                # Execute tools
                tool_results = []
                for tool_call in tool_calls:
                    try:
                        result = self._execute_tool(
                            tool_call["name"],
                            tool_call["input"],
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call["id"],
                                "content": result,
                            }
                        )
                        all_tool_calls.append(
                            ToolExecution(
                                tool_name=tool_call["name"],
                                input_json=tool_call["input"],
                                output_json=result,
                                status="succeeded",
                            )
                        )
                    except Exception as e:
                        logger.error("[%s] Tool %s failed: %s", self.name, tool_call["name"], e)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call["id"],
                                "content": f"Error: {e!s}",
                                "is_error": True,
                            }
                        )
                        all_tool_calls.append(
                            ToolExecution(
                                tool_name=tool_call["name"],
                                input_json=tool_call["input"],
                                output_json=str(e),
                                status="failed",
                                error=str(e),
                            )
                        )

                # Add tool results to messages
                messages.append({"role": "user", "content": tool_results})

            except Exception as e:
                logger.error("[%s] Attempt %d failed: %s", self.name, attempt, e)
                trace = traceback.format_exc()

                if error_mapping.should_retry(e):
                    if attempt < self.config.max_retries:
                        continue
                    return AgentRunResult(
                        output=f"Failed after {attempt} retries: {e!s}",
                        success=False,
                        error=str(e),
                        metadata={
                            "attempts": attempt,
                            "trace": trace,
                            "model": self.model,
                        },
                    )

                if error_mapping.should_fail(e):
                    return AgentRunResult(
                        output=f"Failed: {e!s}",
                        success=False,
                        error=str(e),
                        metadata={
                            "trace": trace,
                            "model": self.model,
                        },
                    )

                raise

        # Fallback (should not reach here)
        return AgentRunResult(
            output="No response generated",
            success=False,
            error="Unexpected: loop exited without return",
        )

    def _get_client(self) -> Any:
        """Get or create Anthropic client."""
        if self._client is None:
            from anthropic import AsyncAnthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY env var not set")

            self._client = AsyncAnthropic(api_key=api_key)

        return self._client

    def _get_tool_schemas(self) -> list[dict[str, Any]]:
        """Convert @tool functions to Claude tool schema."""
        tool_schemas = []

        for tool_func in self.tools:
            if not hasattr(tool_func, "_tool_metadata"):
                continue

            meta = tool_func._tool_metadata
            schema = {
                "name": meta["name"],
                "description": meta["description"],
                "input_schema": {
                    "type": "object",
                    "properties": meta.get("parameters", {}),
                    "required": meta.get("required", []),
                },
            }
            tool_schemas.append(schema)

        return tool_schemas

    def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool by name."""
        for tool_func in self.tools:
            if hasattr(tool_func, "_tool_metadata") and tool_func._tool_metadata["name"] == tool_name:
                result = tool_func(**tool_input)
                return str(result)

        raise ValueError(f"Tool not found: {tool_name}")


__all__ = ["FlintAnthropicAgent"]
