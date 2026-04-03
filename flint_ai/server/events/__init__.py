"""Redis Pub/Sub event bus for cross-pod SSE notifications.

When a task changes state on Pod A, it publishes to a Redis channel.
All pods subscribe and relay events to their local SSE clients.
This replaces the in-memory subscriber dict for multi-pod deployments.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Callable

logger = logging.getLogger("flint.server.events.pubsub")

CHANNEL_PREFIX = "flint:events:"


class RedisPubSubBus:
    """Cross-pod event bus backed by Redis Pub/Sub."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client
        self._pubsub: Any = None
        self._subscribers: dict[str, list[Callable]] = {}
        self._listen_task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Start listening for events on Redis Pub/Sub."""
        self._pubsub = self._redis.pubsub()
        await self._pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
        self._running = True
        self._listen_task = asyncio.create_task(self._listen())
        logger.info("Redis Pub/Sub event bus started")

    async def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
        if self._pubsub:
            await self._pubsub.punsubscribe()
            await self._pubsub.aclose()
        logger.info("Redis Pub/Sub event bus stopped")

    async def publish(self, task_id: str, event: str, data: dict[str, Any]) -> None:
        """Publish a task event to Redis (all pods receive it)."""
        channel = f"{CHANNEL_PREFIX}{task_id}"
        payload = json.dumps({"event": event, "task_id": task_id, "data": data})
        await self._redis.publish(channel, payload)

    def subscribe(self, task_id: str, callback: Callable) -> None:
        """Subscribe to task events (local callback, fed by Redis)."""
        if task_id not in self._subscribers:
            self._subscribers[task_id] = []
        self._subscribers[task_id].append(callback)

    def unsubscribe(self, task_id: str, callback: Callable) -> None:
        """Remove a local subscriber."""
        if task_id in self._subscribers:
            self._subscribers[task_id] = [cb for cb in self._subscribers[task_id] if cb is not callback]
            if not self._subscribers[task_id]:
                del self._subscribers[task_id]

    async def _listen(self) -> None:
        """Background task: read Redis messages and dispatch to local subscribers."""
        while self._running:
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "pmessage":
                    try:
                        payload = json.loads(message["data"])
                        task_id = payload.get("task_id", "")
                        event = payload.get("event", "")
                        data = payload.get("data", {})
                        await self._dispatch(task_id, event, data)
                    except (json.JSONDecodeError, KeyError):
                        logger.warning("Invalid Pub/Sub message: %s", message["data"])
                else:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Pub/Sub listener error")
                await asyncio.sleep(1)

    async def _dispatch(self, task_id: str, event: str, data: dict[str, Any]) -> None:
        """Dispatch event to local subscribers for this task_id."""
        callbacks = self._subscribers.get(task_id, [])
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event, data)
                else:
                    cb(event, data)
            except Exception:
                logger.exception("Subscriber error for task=%s", task_id)
