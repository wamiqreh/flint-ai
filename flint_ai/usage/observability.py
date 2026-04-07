"""Observability hooks for real-time monitoring and debugging."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from .events import AIEvent

logger = logging.getLogger("flint.usage.observability")


class ObservabilityHooks:
    """Hooks for real-time monitoring, debugging, and event streaming.

    Usage:
        hooks = ObservabilityHooks()
        hooks.add_listener(lambda e: print(f"Cost: ${e.cost_usd}"))
        hooks.on_event(event)
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[[AIEvent], Awaitable[None] | None]] = []
        self._stream_queues: list[asyncio.Queue[AIEvent | None]] = []

    def add_listener(self, callback: Callable[[AIEvent], Awaitable[None] | None]) -> None:
        """Register a custom event listener."""
        self._listeners.append(callback)
        logger.debug("Observability listener registered (total=%d)", len(self._listeners))

    def remove_listener(self, callback: Callable[[AIEvent], Awaitable[None] | None]) -> None:
        """Remove a previously registered listener."""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass

    async def on_event(self, event: AIEvent) -> None:
        """Called for every event. Notifies all listeners."""
        tasks = []
        for listener in self._listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    tasks.append(result)
            except Exception:
                logger.exception("Error in observability listener for event %s", event.id)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.exception("Observability listener raised")

        for q in self._stream_queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def cost_stream(self, max_size: int = 1000) -> AsyncIterator[AIEvent]:
        """Real-time cost event stream.

        Usage:
            async for event in hooks.cost_stream():
                print(f"Event: {event.type} cost=${event.cost_usd}")
        """
        q: asyncio.Queue[AIEvent | None] = asyncio.Queue(maxsize=max_size)
        self._stream_queues.append(q)
        try:
            return self._stream_iterator(q)
        finally:
            self._stream_queues.remove(q)

    async def _stream_iterator(self, q: asyncio.Queue[AIEvent | None]) -> AsyncIterator[AIEvent]:
        try:
            while True:
                event = await q.get()
                if event is None:
                    break
                yield event
        except asyncio.CancelledError:
            pass

    def debug_log(self, event: AIEvent) -> str:
        """Human-readable debug line for an event."""
        parts = [
            f"[{event.type.value}]",
            f"provider={event.provider}",
            f"model={event.model}",
        ]
        if event.input_tokens is not None:
            parts.append(f"in={event.input_tokens}")
        if event.output_tokens is not None:
            parts.append(f"out={event.output_tokens}")
        if event.estimated:
            parts.append("[ESTIMATED]")
        if event.cost_usd is not None:
            parts.append(f"cost=${event.cost_usd:.6f}")
        return " ".join(parts)

    def log_event(self, event: AIEvent, level: int = logging.DEBUG) -> None:
        """Log an event at the specified level."""
        logger.log(level, self.debug_log(event))

    @property
    def listener_count(self) -> int:
        return len(self._listeners)
