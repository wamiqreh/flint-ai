"""In-memory queue adapter for development and testing."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from typing import Any, Dict, List

from flint_ai.server.queue import BaseQueue, QueueMessage

logger = logging.getLogger("flint.server.queue.memory")


class InMemoryQueue(BaseQueue):
    """Thread-safe in-memory queue using asyncio primitives.

    Suitable for development and single-process deployments.
    Does NOT survive process restarts.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[QueueMessage] = asyncio.Queue()
        self._pending: Dict[str, QueueMessage] = {}
        self._dlq: Dict[str, QueueMessage] = {}
        self._event = asyncio.Event()

    async def enqueue(self, task_id: str, data: Dict[str, Any], priority: int = 0) -> str:
        msg_id = str(uuid.uuid4())
        msg = QueueMessage(
            message_id=msg_id,
            task_id=task_id,
            data=data,
            attempt=data.get("attempt", 0),
        )
        await self._queue.put(msg)
        self._event.set()
        logger.debug("Enqueued task=%s msg=%s", task_id, msg_id)
        return msg_id

    async def dequeue(self, count: int = 1, block_ms: int = 5000) -> List[QueueMessage]:
        messages: List[QueueMessage] = []
        timeout = block_ms / 1000.0

        for _ in range(count):
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                self._pending[msg.message_id] = msg
                messages.append(msg)
                # Subsequent gets shouldn't block as long
                timeout = 0.01
            except asyncio.TimeoutError:
                break

        if not messages:
            self._event.clear()

        return messages

    async def ack(self, message_id: str) -> None:
        self._pending.pop(message_id, None)
        logger.debug("Acked msg=%s", message_id)

    async def nack(self, message_id: str) -> None:
        msg = self._pending.pop(message_id, None)
        if msg:
            msg.attempt += 1
            msg.data["attempt"] = msg.attempt
            await self._queue.put(msg)
            logger.debug("Nacked msg=%s, requeued attempt=%d", message_id, msg.attempt)

    async def move_to_dlq(self, message_id: str, reason: str = "") -> None:
        msg = self._pending.pop(message_id, None)
        if msg:
            msg.data["dlq_reason"] = reason
            self._dlq[msg.message_id] = msg
            logger.info("Moved to DLQ: msg=%s task=%s reason=%s", message_id, msg.task_id, reason)

    async def get_queue_length(self) -> int:
        return self._queue.qsize()

    async def get_dlq_length(self) -> int:
        return len(self._dlq)

    async def get_dlq_messages(self, count: int = 50) -> List[QueueMessage]:
        return list(self._dlq.values())[:count]

    async def retry_dlq_message(self, message_id: str) -> str:
        msg = self._dlq.pop(message_id, None)
        if not msg:
            raise KeyError(f"DLQ message {message_id} not found")
        new_id = await self.enqueue(msg.task_id, msg.data)
        logger.info("Retried DLQ msg=%s → new=%s", message_id, new_id)
        return new_id

    async def purge_dlq(self) -> int:
        count = len(self._dlq)
        self._dlq.clear()
        logger.info("Purged %d DLQ messages", count)
        return count
