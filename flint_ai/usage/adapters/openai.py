"""OpenAI adapter for the unified usage tracking system.

Wraps the OpenAI SDK to provide standardized LLM/embedding/image/audio calls
with automatic usage extraction, cost calculation, and event emission.

Usage:
    from flint_ai.usage import PricingRegistry, CostEngine, EventEmitter
    from flint_ai.usage.adapters.openai import OpenAIAdapter

    pricing = PricingRegistry()
    emitter = EventEmitter()
    adapter = OpenAIAdapter(api_key="sk-...", pricing=pricing, emitter=emitter)

    result = await adapter.execute_llm("gpt-4o", messages=[
        {"role": "user", "content": "Hello"}
    ])
    print(f"Cost: ${result.cost_usd}, Tokens: {result.usage.total_tokens}")
"""

from __future__ import annotations

import logging
from typing import Any

from ..cost_engine import CostEngine
from ..events import AIEvent, EventEmitter, EventType
from ..normalizer import Normalizer
from ..pricing import PricingRegistry
from .base import (
    AIAdapter,
    AudioResponse,
    EmbeddingResponse,
    ImageResponse,
    LLMResponse,
    UsageInfo,
)

logger = logging.getLogger("flint.usage.adapters.openai")


class OpenAIAdapter(AIAdapter):
    """OpenAI adapter with automatic usage tracking and cost calculation.

    Features:
    - Wraps chat.completions, embeddings, images, and audio calls
    - Extracts usage from response.usage
    - Falls back to estimation if usage is missing
    - Emits AIEvents for every call
    - Calculates cost via CostEngine
    - Supports tool calling loops (each round emits its own event)
    """

    def __init__(
        self,
        api_key: str,
        pricing: PricingRegistry,
        emitter: EventEmitter | None = None,
        base_url: str | None = None,
        organization: str | None = None,
        project: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._organization = organization
        self._project = project
        self.pricing = pricing
        self.emitter = emitter or EventEmitter()
        self.cost_engine = CostEngine(pricing)
        self.normalizer = Normalizer()
        self._client: Any = None

    @property
    def provider(self) -> str:
        return "openai"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError("openai package required. Install with: pip install flint-ai[openai]")
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            if self._organization:
                kwargs["organization"] = self._organization
            if self._project:
                kwargs["project"] = self._project
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def execute_llm(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute a chat completion call with usage tracking.

        Supports tool calling loops. Each round emits its own AIEvent.
        """
        client = self._get_client()
        tool_schemas = kwargs.pop("tools", None)
        max_tool_rounds = kwargs.pop("max_tool_rounds", 10)
        tool_results: list[dict[str, Any]] = []

        all_input_tokens = 0
        all_output_tokens = 0
        all_cached_tokens = 0
        content = ""
        finish_reason = None
        raw_response = None

        for round_idx in range(max_tool_rounds):
            call_kwargs = {
                "model": model,
                "messages": messages,
                **kwargs,
            }
            if tool_schemas:
                call_kwargs["tools"] = tool_schemas

            response = await client.chat.completions.create(**call_kwargs)
            raw_response = response
            choice = response.choices[0]

            if response.usage:
                all_input_tokens += response.usage.prompt_tokens or 0
                all_output_tokens += response.usage.completion_tokens or 0
                if hasattr(response.usage, "prompt_tokens_details") and response.usage.prompt_tokens_details:
                    cached = getattr(response.usage.prompt_tokens_details, "cached_tokens", 0) or 0
                    all_cached_tokens += cached

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message.model_dump())

                for tool_call in choice.message.tool_calls:
                    fn_name = tool_call.function.name
                    fn_args = tool_call.function.arguments

                    tool_event = self.normalizer.normalize_tool_call(
                        provider=self.provider,
                        model=model,
                        tool_name=fn_name,
                        metadata={
                            "tool_args": fn_args,
                            "round": round_idx,
                        },
                    )
                    tool_cost = self.cost_engine.calculate(tool_event)
                    tool_event = tool_event.with_cost(tool_cost)
                    await self.emitter.emit_async(tool_event)
                    tool_results.append(
                        {
                            "tool_name": fn_args,
                            "cost_usd": tool_cost,
                        }
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Tool {fn_name} executed",
                    }
                )
                continue

            content = choice.message.content or ""
            finish_reason = choice.finish_reason
            break

        usage = UsageInfo(
            input_tokens=all_input_tokens if all_input_tokens else None,
            output_tokens=all_output_tokens if all_output_tokens else None,
            cached_tokens=all_cached_tokens if all_cached_tokens else None,
        )

        input_text = " ".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))
        event = self.normalizer.normalize_llm(
            provider=self.provider,
            model=model,
            input_text=input_text,
            output_text=content,
            usage={
                "prompt_tokens": all_input_tokens if all_input_tokens else None,
                "completion_tokens": all_output_tokens if all_output_tokens else None,
                "cached_tokens": all_cached_tokens if all_cached_tokens else None,
            },
            metadata={
                "tool_rounds": round_idx,
                "tool_results": tool_results,
                "finish_reason": finish_reason,
            },
        )

        cost = self.cost_engine.calculate(event)
        event = event.with_cost(cost)
        await self.emitter.emit_async(event)

        return LLMResponse(
            content=content,
            usage=usage,
            finish_reason=finish_reason,
            raw=raw_response,
        )

    async def execute_embedding(
        self,
        model: str,
        input: str | list[str],
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """Execute an embedding call with usage tracking."""
        client = self._get_client()
        response = await client.embeddings.create(model=model, input=input, **kwargs)

        usage_info = self.extract_usage(response)
        input_text = input if isinstance(input, str) else " ".join(input)

        event = self.normalizer.normalize_embedding(
            provider=self.provider,
            model=model,
            input_text=input_text,
            usage={
                "prompt_tokens": usage_info.input_tokens,
                "completion_tokens": usage_info.output_tokens,
            },
        )

        cost = self.cost_engine.calculate(event)
        event = event.with_cost(cost)
        await self.emitter.emit_async(event)

        embeddings = [d.embedding for d in response.data]
        return EmbeddingResponse(
            embeddings=embeddings,
            usage=usage_info,
            raw=response,
        )

    async def execute_image(
        self,
        model: str = "dall-e-3",
        prompt: str = "",
        n: int = 1,
        size: str = "1024x1024",
        **kwargs: Any,
    ) -> ImageResponse:
        """Execute an image generation call with usage tracking."""
        client = self._get_client()
        response = await client.images.generate(model=model, prompt=prompt, n=n, size=size, **kwargs)

        event = self.normalizer.normalize_image(
            provider=self.provider,
            model=model,
            image_count=n,
            metadata={"prompt": prompt, "size": size},
        )

        cost = self.cost_engine.calculate(event)
        event = event.with_cost(cost)
        await self.emitter.emit_async(event)

        urls = [img.url for img in response.data if img.url]
        b64 = [img.b64_json for img in response.data if img.b64_json]
        return ImageResponse(urls=urls, b64_json=b64, raw=response)

    async def execute_audio_transcription(
        self,
        model: str = "whisper-1",
        file: Any = None,
        **kwargs: Any,
    ) -> AudioResponse:
        """Execute an audio transcription call with usage tracking."""
        client = self._get_client()
        response = await client.audio.transcriptions.create(model=model, file=file, **kwargs)

        text = response.text if hasattr(response, "text") else str(response)

        event = AIEvent(
            provider=self.provider,
            model=model,
            type=EventType.AUDIO,
            metadata={"audio_duration_seconds": kwargs.get("duration_seconds", 0)},
        )

        cost = self.cost_engine.calculate(event)
        event = event.with_cost(cost)
        await self.emitter.emit_async(event)

        return AudioResponse(text=text, raw=response)

    def extract_usage(self, response: Any) -> UsageInfo:
        """Extract token usage from an OpenAI response."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return UsageInfo()

        cached = 0
        if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0

        return UsageInfo(
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
            cached_tokens=cached if cached else None,
        )
