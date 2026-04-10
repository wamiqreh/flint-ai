"""Flint Anthropic (Claude) Adapter — run Claude agents as Flint tasks.

This adapter wraps the Anthropic Claude API, giving you the natural Anthropic developer
experience with Flint's queue, retry, DAG, and approval infrastructure.

Supports Claude 3 and 3.5 models with tool calling, vision, and streaming.

Usage:
    from flint_ai.adapters.anthropic import FlintAnthropicAgent
    from flint_ai.adapters.openai import tool

    @tool
    def search_docs(query: str) -> str:
        return "search results..."

    agent = FlintAnthropicAgent(
        name="doc_analyst",
        model="claude-3-5-sonnet-20241022",
        instructions="You are a document analyst.",
        tools=[search_docs],
    )

    # Use in a workflow
    from flint_ai import Workflow, Node
    wf = (Workflow("analysis")
        .add(Node("analyze", agent=agent, prompt="Analyze this document"))
        .build())
"""

from __future__ import annotations

import json
import logging
import os
import time
import traceback
from collections.abc import Callable
from typing import Any

from ..core.base import FlintAdapter
from ..core.cost_tracker import FlintCostTracker
from ..core.sanitization import sanitize_input
from ..core.types import AdapterConfig, AgentRunResult, ErrorMapping, ToolExecution
from ..openai.tools import execute_tool_call, get_tool_schemas

logger = logging.getLogger("flint.adapters.anthropic")

# Anthropic error mapping
_ANTHROPIC_ERROR_MAPPING: ErrorMapping | None = None


def _get_anthropic_error_mapping() -> ErrorMapping:
    """Build error mapping, importing Anthropic errors only if available."""
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

        retry_on.extend([APITimeoutError, APIConnectionError, AuthenticationError, APIStatusError])
        fail_on.append(BadRequestError)
    except ImportError:
        pass

    _ANTHROPIC_ERROR_MAPPING = ErrorMapping(retry_on=retry_on, fail_on=fail_on)
    return _ANTHROPIC_ERROR_MAPPING


def _convert_tool_schemas_to_anthropic(tool_schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-style tool schemas to Anthropic format.

    OpenAI format: {"type": "function", "function": {"name": "...", "parameters": {...}}}
    Anthropic format: {"name": "...", "description": "...", "input_schema": {...}}
    """
    anthropic_tools = []
    for schema in tool_schemas:
        if "function" in schema:
            func = schema["function"]
            anthropic_tools.append(
                {
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                }
            )
    return anthropic_tools


class FlintAnthropicAgent(FlintAdapter):
    """Wrap a Claude model (with optional tools) as a Flint agent.

    Supports Claude 3, 3.5, and earlier models with tool calling and vision.
    Uses the same @tool decorator as FlintOpenAIAgent for seamless compatibility.

    Args:
        name: Agent name for Flint registration (e.g., "doc_analyst").
        model: Claude model ID (e.g., "claude-3-5-sonnet-20241022").
        instructions: System prompt / agent instructions.
        tools: List of @tool-decorated functions.
        temperature: Sampling temperature (0.0 - 1.0).
        max_tokens: Maximum tokens in response.
        api_key: Anthropic API key (default: ANTHROPIC_API_KEY env var).
        max_tool_rounds: Max tool call rounds before forcing a final answer.
        cost_tracker: FlintCostTracker for cost calculation (injected).
        config: Flint adapter config override.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str = "claude-3-5-sonnet-20241022",
        instructions: str = "You are a helpful assistant.",
        tools: list[Callable] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        api_key: str | None = None,
        max_tool_rounds: int = 10,
        cost_tracker: FlintCostTracker | None = None,
        config: AdapterConfig | None = None,
    ):
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
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.max_tool_rounds = max_tool_rounds
        self.cost_tracker = cost_tracker or FlintCostTracker()

    async def run(self, input_data: dict[str, Any]) -> AgentRunResult:
        """Execute the Claude agent."""
        prompt = input_data.get("prompt", "")

        if not self.api_key:
            return AgentRunResult(
                output="",
                success=False,
                error=(
                    "ANTHROPIC_API_KEY not set. Set it as an environment variable or pass "
                    "api_key= to FlintAnthropicAgent."
                ),
            )

        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            return AgentRunResult(
                output="",
                success=False,
                error="anthropic package not installed. Run: pip install anthropic",
            )

        client = AsyncAnthropic(api_key=self.api_key)
        tool_schemas = get_tool_schemas(self.tools)
        anthropic_tools = _convert_tool_schemas_to_anthropic(tool_schemas) if tool_schemas else []

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        task_id = input_data.get("task_id", "")
        workflow_run_id = input_data.get("metadata", {}).get("workflow_run_id")
        node_id = input_data.get("node_id")

        tool_executions: list[ToolExecution] = []
        total_input_tokens = 0
        total_output_tokens = 0

        for _round in range(self.max_tool_rounds):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": self.instructions,
                "messages": messages,
                "temperature": self.temperature,
            }
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools

            response = await client.messages.create(**kwargs)

            if response.usage:
                total_input_tokens += response.usage.input_tokens or 0
                total_output_tokens += response.usage.output_tokens or 0

            # Check if we have tool uses in the response
            tool_use_blocks = [
                block for block in response.content if hasattr(block, "type") and block.type == "tool_use"
            ]

            if tool_use_blocks:
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for tool_use in tool_use_blocks:
                    tool_name = tool_use.name
                    tool_input = tool_use.input
                    start_time = time.monotonic()

                    try:
                        result = await execute_tool_call(self.tools, tool_name, tool_input)
                        duration_ms = (time.monotonic() - start_time) * 1000

                        tool_exec = ToolExecution(
                            task_id=task_id,
                            workflow_run_id=workflow_run_id,
                            node_id=node_id,
                            tool_name=tool_name,
                            input_json=tool_input,
                            output_json=result,
                            duration_ms=round(duration_ms, 2),
                            status="succeeded",
                            sanitized_input=sanitize_input(tool_input),
                        )
                        tool_executions.append(tool_exec)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": result,
                            }
                        )

                    except Exception as e:
                        duration_ms = (time.monotonic() - start_time) * 1000
                        result = json.dumps({"error": str(e), "tool_name": tool_name})

                        tool_exec = ToolExecution(
                            task_id=task_id,
                            workflow_run_id=workflow_run_id,
                            node_id=node_id,
                            tool_name=tool_name,
                            input_json=tool_input,
                            output_json=result,
                            duration_ms=round(duration_ms, 2),
                            error=str(e),
                            stack_trace=traceback.format_exc(),
                            status="failed",
                            sanitized_input=sanitize_input(tool_input),
                        )
                        tool_executions.append(tool_exec)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use.id,
                                "content": result,
                                "is_error": True,
                            }
                        )

                messages.append({"role": "user", "content": tool_results})
                continue

            # Final text response (no more tool calls)
            text_content = ""
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    text_content += block.text

            cost = self.cost_tracker.calculate(
                self.model,
                prompt_tokens=total_input_tokens,
                completion_tokens=total_output_tokens,
            )

            return AgentRunResult(
                output=text_content,
                cost=cost,
                metadata={
                    "model": self.model,
                    "usage": {
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                    },
                    "tool_rounds": _round,
                    "tool_executions": [e.to_dict() for e in tool_executions],
                },
            )

        # Max tool rounds exceeded
        cost = self.cost_tracker.calculate(
            self.model,
            prompt_tokens=total_input_tokens,
            completion_tokens=total_output_tokens,
        )
        return AgentRunResult(
            output="Max tool rounds exceeded",
            success=False,
            error=f"Agent exceeded {self.max_tool_rounds} tool calling rounds",
            cost=cost,
            metadata={
                "model": self.model,
                "tool_rounds": self.max_tool_rounds,
                "tool_executions": [e.to_dict() for e in tool_executions],
            },
        )

    def to_registered_agent(self):
        from ..core.types import RegisteredAgent

        return RegisteredAgent(
            name=self._name,
            inline=self._config.inline,
            adapter_type="FlintAnthropicAgent",
        )
