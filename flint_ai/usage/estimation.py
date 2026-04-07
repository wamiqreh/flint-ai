"""Token estimation fallback when provider doesn't return usage data."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("flint.usage.estimation")


class UsageInfo:
    """Token usage information."""

    def __init__(
        self,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_tokens: int | None = None,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cached_tokens = cached_tokens

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens or 0) + (self.output_tokens or 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "total_tokens": self.total_tokens,
        }


_CHARS_PER_TOKEN = 4.0


class TokenEstimator:
    """Estimate token usage when provider doesn't return actual counts.

    Uses tiktoken for OpenAI models when available, falls back to
    character-based heuristic (~4 chars per token) for everything else.
    """

    def __init__(self) -> None:
        self._tiktoken_available = False
        try:
            import tiktoken  # noqa: F401

            self._tiktoken_available = True
        except ImportError:
            pass

    def estimate(
        self,
        provider: str,
        model: str,
        input_text: str,
        output_text: str | None = None,
    ) -> UsageInfo:
        """Estimate token usage for the given text.

        Args:
            provider: Provider namespace (e.g., "openai").
            model: Model identifier (e.g., "gpt-4o").
            input_text: The input/prompt text.
            output_text: The output/completion text (if available).

        Returns:
            UsageInfo with estimated token counts.
        """
        if self._tiktoken_available and provider == "openai":
            return self._estimate_openai(model, input_text, output_text)
        return self._estimate_generic(input_text, output_text)

    def _estimate_openai(
        self,
        model: str,
        input_text: str,
        output_text: str | None = None,
    ) -> UsageInfo:
        """Use tiktoken for accurate OpenAI token estimation."""
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")

        input_tokens = len(enc.encode(input_text))
        output_tokens = len(enc.encode(output_text)) if output_text else 0

        logger.debug(
            "Estimated tokens via tiktoken: input=%d, output=%d, model=%s",
            input_tokens,
            output_tokens,
            model,
        )
        return UsageInfo(input_tokens=input_tokens, output_tokens=output_tokens)

    def _estimate_generic(
        self,
        input_text: str,
        output_text: str | None = None,
    ) -> UsageInfo:
        """Fallback: character-based heuristic (~4 chars per token)."""
        input_tokens = max(1, int(len(input_text) / _CHARS_PER_TOKEN))
        output_tokens = int(len(output_text) / _CHARS_PER_TOKEN) if output_text else 0

        logger.debug(
            "Estimated tokens via char heuristic: input=%d, output=%d",
            input_tokens,
            output_tokens,
        )
        return UsageInfo(input_tokens=input_tokens, output_tokens=output_tokens)
