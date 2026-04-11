"""Anthropic (Claude) adapter for the unified usage tracking system.

Wraps the Anthropic SDK to provide standardized LLM calls with automatic
usage extraction, cost calculation, and event emission.

Usage:
    from flint_ai.usage import PricingRegistry, CostEngine, EventEmitter
    from flint_ai.usage.adapters.anthropic import AnthropicAdapter

    pricing = PricingRegistry()
    emitter = EventEmitter()
    adapter = AnthropicAdapter(api_key="sk-ant-...", pricing=pricing, emitter=emitter)

    result = await adapter.execute_llm("claude-3-5-sonnet-20241022", messages=[
        {"role": "user", "content": "Hello"}
    ])
    print(f"Cost: ${result.cost_usd}, Tokens: {result.usage.total_tokens}")
"""

from __future__ import annotations

import logging
from typing import Any

from ..cost_engine import CostEngine
from ..events import EventEmitter
from ..normalizer import Normalizer
from ..pricing import PricingRegistry
from .base import AIAdapter, LLMResponse, UsageInfo

logger = logging.getLogger("flint.usage.adapters.anthropic")


class AnthropicAdapter(AIAdapter):
    """Anthropic Claude adapter with automatic usage tracking and cost calculation.

    Features:
    - Wraps Claude LLM calls
    - Extracts usage from response.usage (input_tokens, output_tokens)
    - Emits AIEvents for every call
    - Calculates cost via CostEngine
    - Supports tool calling loops
    """

    def __init__(
        self,
        api_key: str,
        pricing: PricingRegistry,
        emitter: EventEmitter | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self.pricing = pricing
        self.emitter = emitter or EventEmitter()
        self.cost_engine = CostEngine(pricing)
        self.normalizer = Normalizer()
        self._client: Any = None

    @property
    def provider(self) -> str:
        return "anthropic"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                raise ImportError("anthropic library required. Install: pip install anthropic")
            self._client = AsyncAnthropic(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    async def execute_llm(
        self,
        model: str,
        messages: list[dict[str, str]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute LLM call with Claude.

        Args:
            model: Model ID (e.g., "claude-3-5-sonnet-20241022").
            messages: Conversation messages.
            system: System prompt.
            tools: Tool definitions (Claude format).
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum output tokens.
            **kwargs: Additional Anthropic API parameters.

        Returns:
            LLMResponse with cost and usage info.
        """
        client = self._get_client()

        try:
            # Call Claude
            response = await client.messages.create(
                model=model,
                messages=messages,
                system=system,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens or 1024,
                **kwargs,
            )

            # Extract usage
            usage_info = self.extract_usage(response)
            input_tokens = usage_info.input_tokens or 0
            output_tokens = usage_info.output_tokens or 0

            # Extract text and tool calls
            text_content = ""
            tool_calls = []

            for block in response.content:
                if hasattr(block, "text"):
                    text_content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

            # Emit event via Normalizer
            input_text = str(messages)  # Convert messages to string for token estimation
            event = self.normalizer.normalize_llm(
                provider="anthropic",
                model=model,
                input_text=input_text,
                output_text=text_content,
                usage={"prompt_tokens": input_tokens, "completion_tokens": output_tokens},
                metadata={"stop_reason": response.stop_reason},
            )

            # Calculate cost
            cost = self.cost_engine.calculate(event)
            event = event.with_cost(cost)
            await self.emitter.emit_async(event)

            return LLMResponse(
                content=text_content,
                usage=usage_info,
                finish_reason=response.stop_reason,
                raw=response,
            )

        except Exception as e:
            logger.error("Claude API error: %s", e)
            raise

    async def execute_embedding(
        self,
        model: str,
        texts: list[str],
        **kwargs: Any,
    ) -> Any:
        """Claude doesn't support embeddings. Raise NotImplementedError."""
        raise NotImplementedError("Claude models do not support embeddings")

    async def execute_image(
        self,
        model: str,
        prompt: str,
        size: str = "1024x1024",
        **kwargs: Any,
    ) -> Any:
        """Claude doesn't support image generation. Raise NotImplementedError."""
        raise NotImplementedError("Claude models do not support image generation")

    async def execute_audio(
        self,
        model: str,
        audio_path: str,
        **kwargs: Any,
    ) -> Any:
        """Claude doesn't support audio transcription. Raise NotImplementedError."""
        raise NotImplementedError("Claude models do not support audio transcription")

    def extract_usage(self, response: Any) -> UsageInfo:
        """Extract token usage from an Anthropic response."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return UsageInfo()

        return UsageInfo(
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            cached_tokens=getattr(usage, "cache_read_input_tokens", None),
        )
