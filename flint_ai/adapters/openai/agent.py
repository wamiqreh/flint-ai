"""Flint OpenAI Adapter — run OpenAI SDK agents as Flint tasks.

This adapter wraps the OpenAI Chat Completions API and (optionally) the
OpenAI Agents SDK, giving you the natural OpenAI developer experience
with Flint's queue, retry, DAG, and approval infrastructure.

Usage:
    from flint_ai.adapters.openai import FlintOpenAIAgent
    from flint_ai import tool

    @tool
    def search_code(query: str) -> str:
        return "results..."

    agent = FlintOpenAIAgent(
        name="code_reviewer",
        model="gpt-4o",
        instructions="You are an expert code reviewer.",
        tools=[search_code],
    )

    # Use in a workflow
    from flint_ai import Workflow, Node
    wf = (Workflow("review-pipeline")
        .add(Node("review", agent=agent, prompt="Review this PR"))
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
from .tools import execute_tool_call, get_tool_schemas

logger = logging.getLogger("flint.adapters.openai")

# OpenAI error mapping — rate limits and server errors retry, bad requests fail
_OPENAI_ERROR_MAPPING: ErrorMapping | None = None


def _get_openai_error_mapping() -> ErrorMapping:
    """Build error mapping, importing OpenAI errors only if available."""
    global _OPENAI_ERROR_MAPPING
    if _OPENAI_ERROR_MAPPING is not None:
        return _OPENAI_ERROR_MAPPING

    retry_on: list[type[Exception]] = [TimeoutError, ConnectionError]
    fail_on: list[type[Exception]] = [ValueError]

    try:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            RateLimitError,
        )

        retry_on.extend([RateLimitError, APITimeoutError, APIConnectionError, AuthenticationError])
        fail_on.append(BadRequestError)
    except ImportError:
        pass

    _OPENAI_ERROR_MAPPING = ErrorMapping(retry_on=retry_on, fail_on=fail_on)
    return _OPENAI_ERROR_MAPPING


class FlintOpenAIAgent(FlintAdapter):
    """Wrap an OpenAI model (with optional tools) as a Flint agent.

    Supports two modes:
    1. **Chat Completions** — direct openai.chat.completions.create with tool calling loop
    2. **Agents SDK** — if `use_agents_sdk=True`, uses the openai-agents library's Runner

    Args:
        name: Agent name for Flint registration (e.g., "code_reviewer").
        model: OpenAI model ID (e.g., "gpt-4o", "gpt-4o-mini").
        instructions: System prompt / agent instructions.
        tools: List of @tool-decorated functions.
        temperature: Sampling temperature (0.0 - 2.0).
        max_tokens: Maximum tokens in response.
        api_key: OpenAI API key (default: OPENAI_API_KEY env var).
        use_agents_sdk: Use OpenAI Agents SDK Runner instead of raw chat completions.
        handoffs: List of other FlintOpenAIAgent instances for agent handoffs (Agents SDK only).
        max_tool_rounds: Max tool call rounds before forcing a final answer.
        response_format: Structured output format. Pass a Pydantic BaseModel class
            for typed responses, or {"type": "json_object"} for raw JSON mode.
        config: Flint adapter config override.
    """

    def __init__(
        self,
        *,
        name: str,
        model: str = "gpt-4o",
        instructions: str = "You are a helpful assistant.",
        tools: list[Callable] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        api_key: str | None = None,
        use_agents_sdk: bool = False,
        handoffs: list[FlintOpenAIAgent] | None = None,
        max_tool_rounds: int = 10,
        response_format: Any = None,
        enable_cost_tracking: bool = True,
        cost_config_override: dict[str, float] | None = None,
        config: AdapterConfig | None = None,
        # Deprecated — still accepted for backward compat
        cost_tracker: FlintCostTracker | None = None,
    ):
        super().__init__(
            name=name,
            config=config,
            error_mapping=_get_openai_error_mapping(),
        )
        self.model = model
        self.instructions = instructions
        self.tools = tools or []
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.use_agents_sdk = use_agents_sdk
        self.handoffs = handoffs or []
        self.max_tool_rounds = max_tool_rounds
        self.response_format = response_format

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
            kwargs: dict = {"model": model, "provider": "openai"}
            if cost_config_override:
                from flint_ai.config.cost_config import CostConfigManager

                CostConfigManager.get_instance().set_pricing(model, cost_config_override)
            self.cost_tracker = FlintCostTracker(**kwargs)
        else:
            self.cost_tracker = None

    async def run(self, input_data: dict[str, Any]) -> AgentRunResult:
        """Execute the OpenAI agent."""
        prompt = input_data.get("prompt", "")

        if not self.api_key:
            return AgentRunResult(
                output="",
                success=False,
                error="OPENAI_API_KEY not set. Set it as an environment variable or pass api_key= to FlintOpenAIAgent.",
            )

        if self.use_agents_sdk:
            return await self._run_agents_sdk(prompt, input_data)
        return await self._run_chat_completions(prompt, input_data)

    async def _run_chat_completions(self, prompt: str, input_data: dict[str, Any]) -> AgentRunResult:
        """Run using the standard OpenAI Chat Completions API with tool loop."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return AgentRunResult(
                output="",
                success=False,
                error="openai package not installed. Run: pip install flint-ai[openai]",
            )

        client = AsyncOpenAI(api_key=self.api_key)
        tool_schemas = get_tool_schemas(self.tools)

        system_content = self.instructions
        if (
            self.response_format
            and isinstance(self.response_format, dict)
            and self.response_format.get("type") == "json_object"
            and "json" not in system_content.lower()
        ):
            system_content += "\n\nRespond in JSON format."

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if tool_schemas:
            kwargs["tools"] = tool_schemas
        if self.response_format is not None:
            try:
                from pydantic import BaseModel as PydanticBase

                if isinstance(self.response_format, type) and issubclass(self.response_format, PydanticBase):
                    kwargs["response_format"] = self.response_format
                else:
                    kwargs["response_format"] = self.response_format
            except ImportError:
                kwargs["response_format"] = self.response_format

        task_id = input_data.get("task_id", "")
        workflow_run_id = input_data.get("metadata", {}).get("workflow_run_id")
        node_id = input_data.get("node_id")

        tool_executions: list[ToolExecution] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for _round in range(self.max_tool_rounds):
            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if response.usage:
                total_prompt_tokens += response.usage.prompt_tokens or 0
                total_completion_tokens += response.usage.completion_tokens or 0

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message.model_dump())

                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = json.loads(tool_call.function.arguments)
                    start_time = time.monotonic()

                    try:
                        result = await execute_tool_call(self.tools, fn_name, fn_args)
                        duration_ms = (time.monotonic() - start_time) * 1000

                        tool_exec = ToolExecution(
                            task_id=task_id,
                            workflow_run_id=workflow_run_id,
                            node_id=node_id,
                            tool_name=fn_name,
                            input_json=fn_args,
                            output_json=result,
                            duration_ms=round(duration_ms, 2),
                            status="succeeded",
                            sanitized_input=sanitize_input(fn_args),
                        )
                        tool_executions.append(tool_exec)

                    except Exception as e:
                        duration_ms = (time.monotonic() - start_time) * 1000
                        result = json.dumps({"error": str(e), "tool_name": fn_name})

                        tool_exec = ToolExecution(
                            task_id=task_id,
                            workflow_run_id=workflow_run_id,
                            node_id=node_id,
                            tool_name=fn_name,
                            input_json=fn_args,
                            output_json=result,
                            duration_ms=round(duration_ms, 2),
                            error=str(e),
                            stack_trace=traceback.format_exc(),
                            status="failed",
                            sanitized_input=sanitize_input(fn_args),
                        )
                        tool_executions.append(tool_exec)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

                kwargs["messages"] = messages
                continue

            # Final text response
            output = choice.message.content or ""
            cost = (
                self.cost_tracker.calculate(
                    self.model,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                )
                if self.cost_tracker
                else None
            )

            return AgentRunResult(
                output=output,
                cost=cost,
                metadata={
                    "model": self.model,
                    "usage": response.usage.model_dump() if response.usage else {},
                    "tool_rounds": _round,
                    "tool_executions": [e.to_dict() for e in tool_executions],
                },
            )

        # Max tool rounds exceeded
        cost = (
            self.cost_tracker.calculate(
                self.model,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
            )
            if self.cost_tracker
            else None
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

    async def _run_agents_sdk(self, prompt: str, input_data: dict[str, Any]) -> AgentRunResult:
        """Run using the OpenAI Agents SDK (agents library)."""
        try:
            from agents import Agent, Runner  # type: ignore[import-untyped]
        except ImportError:
            return AgentRunResult(
                output="",
                success=False,
                error="openai-agents package not installed. Run: pip install openai-agents",
            )

        handoff_agents = []
        for h in self.handoffs:
            handoff_agents.append(
                Agent(
                    name=h.name,
                    model=h.model,
                    instructions=h.instructions,
                    tools=[t for t in h.tools if hasattr(t, "_flint_tool")],
                )
            )

        agent = Agent(
            name=self.name,
            model=self.model,
            instructions=self.instructions,
            tools=[t for t in self.tools if hasattr(t, "_flint_tool")],
            handoffs=handoff_agents if handoff_agents else [],
        )

        result = await Runner.run(agent, prompt)

        usage = getattr(result, "usage", None)
        cost = None
        if usage and self.cost_tracker:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            cost = self.cost_tracker.calculate(
                self.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        return AgentRunResult(
            output=result.final_output,
            cost=cost,
            metadata={
                "model": self.model,
                "agent_name": self.name,
                "sdk": "openai-agents",
            },
        )

    def to_registered_agent(self):
        from ..core.types import RegisteredAgent

        return RegisteredAgent(
            name=self._name,
            inline=self._config.inline,
            adapter_type="FlintOpenAIAgent",
        )
