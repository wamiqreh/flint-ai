"""AI usage event model and event emitter."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("flint.usage.events")


class EventType(str, Enum):
    """Types of AI usage events."""

    LLM_CALL = "llm_call"
    EMBEDDING = "embedding"
    TOOL_CALL = "tool_call"
    WEB_SEARCH = "web_search"
    IMAGE = "image"
    AUDIO = "audio"


class AIEvent(BaseModel):
    """Universal AI usage event.

    Every interaction with an AI provider is represented as an AIEvent.
    This allows uniform tracking across providers, models, and event types.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = Field(default_factory=time.time)

    provider: str  # "openai", "anthropic", etc.
    model: str  # "gpt-4o", "claude-3-sonnet", etc.
    type: EventType

    input_tokens: int | None = None
    output_tokens: int | None = None

    estimated: bool = False
    cost_usd: float | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return (self.input_tokens or 0) + (self.output_tokens or 0)

    def with_cost(self, cost_usd: float) -> AIEvent:
        """Return a new event with cost attached."""
        return self.model_copy(update={"cost_usd": cost_usd})

    def with_metadata(self, **kwargs: Any) -> AIEvent:
        """Return a new event with additional metadata."""
        meta = {**self.metadata, **kwargs}
        return self.model_copy(update={"metadata": meta})

    def is_estimated(self) -> bool:
        """Whether this event's token counts are estimated."""
        return self.estimated or self.input_tokens is None or self.output_tokens is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "type": self.type.value,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated": self.estimated,
            "cost_usd": self.cost_usd,
            "metadata": self.metadata,
        }


class EventEmitter:
    """Async pub/sub event emitter for AI usage events.

    Events are dispatched to all registered listeners. Listeners are called
    concurrently and failures in one listener do not affect others.

    Usage:
        emitter = EventEmitter()
        emitter.subscribe(lambda e: print(f"Event: {e.type} cost=${e.cost_usd}"))
        emitter.emit(AIEvent(...))
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[[AIEvent], Awaitable[None] | None]] = []
        self._history: list[AIEvent] = []
        self._max_history = 10_000

    def subscribe(self, callback: Callable[[AIEvent], Awaitable[None] | None]) -> None:
        """Register a callback to be called for every emitted event."""
        self._listeners.append(callback)
        logger.debug("Subscriber registered (total=%d)", len(self._listeners))

    def unsubscribe(self, callback: Callable[[AIEvent], Awaitable[None] | None]) -> None:
        """Remove a previously registered callback."""
        try:
            self._listeners.remove(callback)
            logger.debug("Subscriber removed (total=%d)", len(self._listeners))
        except ValueError:
            pass

    def emit(self, event: AIEvent) -> None:
        """Emit an event to all listeners (sync dispatch).

        Listeners that are async coroutines are scheduled via asyncio.create_task
        if an event loop is running. Sync listeners are called directly.
        """
        self._record(event)
        self._background_tasks: set = getattr(self, "_background_tasks", set())
        for listener in self._listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(result)
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)
                    except RuntimeError:
                        pass
            except Exception:
                logger.exception("Error in event listener for event %s", event.id)

    async def emit_async(self, event: AIEvent) -> None:
        """Emit an event to all listeners (async dispatch).

        All listeners are awaited concurrently. Failures are logged but do not
        prevent other listeners from receiving the event.
        """
        self._record(event)
        tasks = []
        for listener in self._listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    tasks.append(result)
                elif asyncio.iscoroutinefunction(listener):
                    tasks.append(listener(event))
            except Exception:
                logger.exception("Error in event listener for event %s", event.id)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.exception("Listener %d raised for event %s", i, event.id)

    def _record(self, event: AIEvent) -> None:
        """Store event in history for replay/aggregation."""
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history // 2 :]

    def get_history(self, limit: int = 100) -> list[AIEvent]:
        """Return recent events from history."""
        return self._history[-limit:]

    def clear_history(self) -> None:
        self._history.clear()

    @property
    def listener_count(self) -> int:
        return len(self._listeners)
