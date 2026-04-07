"""AI adapter contract — strict interface for any AI provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class UsageInfo(BaseModel):
    """Token usage information extracted from a provider response."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None


class LLMResponse(BaseModel):
    """Standardized LLM response."""

    content: str
    usage: UsageInfo | None = None
    finish_reason: str | None = None
    raw: Any = None


class EmbeddingResponse(BaseModel):
    """Standardized embedding response."""

    embeddings: list[list[float]]
    usage: UsageInfo | None = None
    raw: Any = None


class ImageResponse(BaseModel):
    """Standardized image generation response."""

    urls: list[str] = []
    b64_json: list[str] = []
    usage: UsageInfo | None = None
    raw: Any = None


class AudioResponse(BaseModel):
    """Standardized audio response."""

    text: str = ""
    duration_seconds: float = 0.0
    usage: UsageInfo | None = None
    raw: Any = None


class AIAdapter(ABC):
    """Abstract contract for AI provider adapters.

    Every adapter must:
    1. Execute LLM/embedding/image/audio calls
    2. Extract usage from provider responses
    3. Optionally estimate usage when not provided
    4. Emit AIEvents through the provided EventEmitter
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider namespace (e.g., 'openai', 'anthropic')."""
        ...

    @abstractmethod
    async def execute_llm(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute an LLM call. Must extract usage and emit event."""
        ...

    @abstractmethod
    async def execute_embedding(
        self,
        model: str,
        input: str | list[str],
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """Execute an embedding call."""
        ...

    @abstractmethod
    def extract_usage(self, response: Any) -> UsageInfo:
        """Extract token usage from a raw provider response."""
        ...

    def estimate_usage(
        self,
        input_text: str,
        output_text: str,
        model: str | None = None,
    ) -> UsageInfo | None:
        """Fallback estimation when usage is missing.

        Returns None if estimation is not available (caller should use
        the shared TokenEstimator as a fallback).
        """
        return None
