"""Abstract queue adapter interface."""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional, Tuple


class QueueMessage:
    """A message dequeued from the queue, carrying task data and an ack token."""

    __slots__ = ("message_id", "task_id", "data", "attempt")

    def __init__(
        self,
        message_id: str,
        task_id: str,
        data: Dict[str, Any],
        attempt: int = 0,
    ) -> None:
        self.message_id = message_id
        self.task_id = task_id
        self.data = data
        self.attempt = attempt


class BaseQueue(abc.ABC):
    """Abstract queue adapter.

    Implementations must support:
    - Reliable delivery (enqueue → dequeue → ack/nack)
    - Dead-letter queue for permanently failed messages
    - Queue length inspection for metrics
    """

    @abc.abstractmethod
    async def enqueue(self, task_id: str, data: Dict[str, Any], priority: int = 0) -> str:
        """Add a task to the queue. Returns a message ID."""

    @abc.abstractmethod
    async def dequeue(self, count: int = 1, block_ms: int = 5000) -> List[QueueMessage]:
        """Fetch up to `count` messages from the queue.

        Should block for up to `block_ms` if the queue is empty.
        Returns an empty list if no messages are available.
        """

    @abc.abstractmethod
    async def ack(self, message_id: str) -> None:
        """Acknowledge successful processing. Removes from pending."""

    @abc.abstractmethod
    async def nack(self, message_id: str) -> None:
        """Negative acknowledgment. Message may be redelivered or sent to DLQ."""

    @abc.abstractmethod
    async def move_to_dlq(self, message_id: str, reason: str = "") -> None:
        """Move a message to the dead-letter queue."""

    @abc.abstractmethod
    async def get_queue_length(self) -> int:
        """Return approximate number of messages waiting in the queue."""

    @abc.abstractmethod
    async def get_dlq_length(self) -> int:
        """Return number of messages in the dead-letter queue."""

    @abc.abstractmethod
    async def get_dlq_messages(self, count: int = 50) -> List[QueueMessage]:
        """Peek at messages in the dead-letter queue."""

    @abc.abstractmethod
    async def retry_dlq_message(self, message_id: str) -> str:
        """Move a DLQ message back to the main queue. Returns new message ID."""

    @abc.abstractmethod
    async def purge_dlq(self) -> int:
        """Delete all DLQ messages. Returns count of purged messages."""

    async def connect(self) -> None:
        """Initialize connections (called on startup)."""

    async def disconnect(self) -> None:
        """Clean up connections (called on shutdown)."""

    async def reclaim_stale(self) -> int:
        """Reclaim messages that have been pending too long. Returns count reclaimed."""
        return 0
