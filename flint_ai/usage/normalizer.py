"""Normalizer — converts provider-specific responses into standard AIEvents."""

from __future__ import annotations

import logging
from typing import Any

from .estimation import TokenEstimator, UsageInfo
from .events import AIEvent, EventType

logger = logging.getLogger("flint.usage.normalizer")


class Normalizer:
    """Normalizes provider-specific responses into standard AIEvents.

    Handles missing fields gracefully and falls back to estimation
    when token counts are not available.

    Usage:
        normalizer = Normalizer()
        event = normalizer.normalize_llm(
            provider="openai",
            model="gpt-4o",
            input_text=prompt,
            output_text=response,
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            metadata={"task_id": "abc"},
        )
    """

    def __init__(self, estimator: TokenEstimator | None = None) -> None:
        self.estimator = estimator or TokenEstimator()

    def normalize_llm(
        self,
        provider: str,
        model: str,
        input_text: str,
        output_text: str,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AIEvent:
        """Normalize an LLM call response into an AIEvent."""
        usage_info = self._extract_usage(usage, provider, model, input_text, output_text)

        meta = metadata or {}
        if usage_info.cached_tokens is not None:
            meta["cached_tokens"] = usage_info.cached_tokens

        return AIEvent(
            provider=provider,
            model=model,
            type=EventType.LLM_CALL,
            input_tokens=usage_info.input_tokens,
            output_tokens=usage_info.output_tokens,
            estimated=usage_info.estimated,
            metadata=meta,
        )

    def normalize_embedding(
        self,
        provider: str,
        model: str,
        input_text: str,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AIEvent:
        """Normalize an embedding call response into an AIEvent."""
        usage_info = self._extract_usage(usage, provider, model, input_text, None)

        return AIEvent(
            provider=provider,
            model=model,
            type=EventType.EMBEDDING,
            input_tokens=usage_info.input_tokens,
            output_tokens=usage_info.output_tokens,
            estimated=usage_info.estimated,
            metadata=metadata or {},
        )

    def normalize_image(
        self,
        provider: str,
        model: str,
        image_count: int = 1,
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AIEvent:
        """Normalize an image generation response into an AIEvent."""
        usage_info = self._extract_usage(usage, provider, model, "", None)
        meta = metadata or {}
        meta["image_count"] = image_count

        return AIEvent(
            provider=provider,
            model=model,
            type=EventType.IMAGE,
            input_tokens=usage_info.input_tokens,
            output_tokens=usage_info.output_tokens,
            metadata=meta,
        )

    def normalize_audio(
        self,
        provider: str,
        model: str,
        duration_seconds: float,
        input_text: str = "",
        output_text: str = "",
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AIEvent:
        """Normalize an audio transcription/generation response into an AIEvent."""
        usage_info = self._extract_usage(usage, provider, model, input_text, output_text)
        meta = metadata or {}
        meta["audio_duration_seconds"] = duration_seconds

        return AIEvent(
            provider=provider,
            model=model,
            type=EventType.AUDIO,
            input_tokens=usage_info.input_tokens,
            output_tokens=usage_info.output_tokens,
            estimated=usage_info.input_tokens is None,
            metadata=meta,
        )

    def normalize_tool_call(
        self,
        provider: str,
        model: str,
        tool_name: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AIEvent:
        """Normalize a tool call into an AIEvent."""
        meta = metadata or {}
        meta["tool_name"] = tool_name

        estimated = input_tokens is None or output_tokens is None

        return AIEvent(
            provider=provider,
            model=model,
            type=EventType.TOOL_CALL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated=estimated,
            metadata=meta,
        )

    def _extract_usage(
        self,
        usage: dict[str, Any] | None,
        provider: str,
        model: str,
        input_text: str,
        output_text: str | None,
    ) -> UsageInfo:
        """Extract or estimate token usage."""
        if usage is not None:
            return UsageInfo(
                input_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
                output_tokens=usage.get("completion_tokens") or usage.get("output_tokens"),
                cached_tokens=usage.get("cached_tokens") or usage.get("prompt_tokens_details", {}).get("cached_tokens"),
            )

        logger.debug(
            "No usage data from %s:%s, falling back to estimation",
            provider,
            model,
        )
        return self.estimator.estimate(provider, model, input_text, output_text)
