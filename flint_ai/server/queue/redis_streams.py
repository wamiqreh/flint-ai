"""Redis Streams queue adapter with consumer groups and DLQ."""

from __future__ import annotations

import contextlib
import logging
import socket
import uuid
from typing import Any

from flint_ai.server.config import RedisConfig
from flint_ai.server.queue import BaseQueue, QueueMessage

logger = logging.getLogger("flint.server.queue.redis")


class RedisStreamsQueue(BaseQueue):
    """Production queue using Redis Streams.

    Features:
    - Consumer groups for distributed workers
    - XAUTOCLAIM for reclaiming stale messages
    - Dedicated DLQ stream for permanently failed messages
    - Atomic operations via Redis commands
    """

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._redis: Any = None
        self._consumer_name = f"{config.consumer_prefix}-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

    async def connect(self) -> None:
        try:
            import redis.asyncio as aioredis
        except ImportError as e:
            raise ImportError(
                "redis package required for Redis queue. Install with: pip install flint-ai[server-redis]"
            ) from e

        self._redis = aioredis.from_url(
            self._config.url,
            decode_responses=True,
            max_connections=20,
        )
        # Create consumer group (MKSTREAM creates the stream if needed)
        try:
            await self._redis.xgroup_create(
                self._config.stream_key,
                self._config.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Created consumer group=%s on stream=%s",
                self._config.consumer_group,
                self._config.stream_key,
            )
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug("Consumer group already exists")
            else:
                raise

        # Create DLQ stream
        dlq_key = f"{self._config.dlq_prefix}:{self._config.stream_key}"
        try:
            await self._redis.xgroup_create(dlq_key, "dlq-readers", id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

        logger.info("Redis queue connected: consumer=%s", self._consumer_name)

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def enqueue(self, task_id: str, data: dict[str, Any], priority: int = 0) -> str:
        import json

        fields = {
            "task_id": task_id,
            "data": json.dumps(data),
            "priority": str(priority),
        }
        msg_id = await self._redis.xadd(
            self._config.stream_key,
            fields,
            maxlen=self._config.max_stream_length,
            approximate=True,
        )
        logger.debug("Enqueued task=%s msg=%s", task_id, msg_id)
        return msg_id

    async def dequeue(self, count: int = 1, block_ms: int = 5000) -> list[QueueMessage]:
        import json

        block = block_ms or self._config.block_ms
        try:
            results = await self._redis.xreadgroup(
                self._config.consumer_group,
                self._consumer_name,
                {self._config.stream_key: ">"},
                count=count,
                block=block,
            )
        except Exception as e:
            logger.error("XREADGROUP failed: %s", e)
            return []

        messages: list[QueueMessage] = []
        if results:
            for _stream, entries in results:
                for msg_id, fields in entries:
                    try:
                        data = json.loads(fields.get("data", "{}"))
                    except json.JSONDecodeError:
                        data = {}
                    messages.append(
                        QueueMessage(
                            message_id=msg_id,
                            task_id=fields.get("task_id", ""),
                            data=data,
                            attempt=data.get("attempt", 0),
                        )
                    )

        return messages

    async def ack(self, message_id: str) -> None:
        await self._redis.xack(
            self._config.stream_key,
            self._config.consumer_group,
            message_id,
        )
        # Remove from stream to free memory
        await self._redis.xdel(self._config.stream_key, message_id)
        logger.debug("Acked msg=%s", message_id)

    async def nack(self, message_id: str) -> None:
        # NACK by not acknowledging — message stays in pending entries list
        # and will be reclaimed by XAUTOCLAIM after idle timeout
        logger.debug("Nacked msg=%s (will be reclaimed)", message_id)

    async def move_to_dlq(self, message_id: str, reason: str = "") -> None:

        # Read the original message data
        msgs = await self._redis.xrange(self._config.stream_key, message_id, message_id)
        if msgs:
            _id, fields = msgs[0]
            dlq_key = f"{self._config.dlq_prefix}:{self._config.stream_key}"
            fields["dlq_reason"] = reason
            fields["original_msg_id"] = message_id
            await self._redis.xadd(dlq_key, fields)

        # Acknowledge and remove from main stream
        await self.ack(message_id)
        logger.info("Moved to DLQ: msg=%s reason=%s", message_id, reason)

    async def get_queue_length(self) -> int:
        return await self._redis.xlen(self._config.stream_key)

    async def get_dlq_length(self) -> int:
        dlq_key = f"{self._config.dlq_prefix}:{self._config.stream_key}"
        try:
            return await self._redis.xlen(dlq_key)
        except Exception:
            return 0

    async def get_dlq_messages(self, count: int = 50) -> list[QueueMessage]:
        import json

        dlq_key = f"{self._config.dlq_prefix}:{self._config.stream_key}"
        try:
            entries = await self._redis.xrange(dlq_key, "-", "+", count=count)
        except Exception:
            return []

        messages: list[QueueMessage] = []
        for msg_id, fields in entries:
            try:
                data = json.loads(fields.get("data", "{}"))
            except json.JSONDecodeError:
                data = {}
            data["dlq_reason"] = fields.get("dlq_reason", "")
            messages.append(
                QueueMessage(
                    message_id=msg_id,
                    task_id=fields.get("task_id", ""),
                    data=data,
                )
            )
        return messages

    async def retry_dlq_message(self, message_id: str) -> str:
        import json

        dlq_key = f"{self._config.dlq_prefix}:{self._config.stream_key}"
        msgs = await self._redis.xrange(dlq_key, message_id, message_id)
        if not msgs:
            raise KeyError(f"DLQ message {message_id} not found")

        _id, fields = msgs[0]
        data = json.loads(fields.get("data", "{}"))
        data.pop("dlq_reason", None)
        task_id = fields.get("task_id", "")

        # Re-enqueue to main stream
        new_id = await self.enqueue(task_id, data)

        # Remove from DLQ
        await self._redis.xdel(dlq_key, message_id)
        logger.info("Retried DLQ msg=%s → new=%s", message_id, new_id)
        return new_id

    async def purge_dlq(self) -> int:
        dlq_key = f"{self._config.dlq_prefix}:{self._config.stream_key}"
        length = await self.get_dlq_length()
        if length > 0:
            await self._redis.delete(dlq_key)
            # Re-create the group
            with contextlib.suppress(Exception):
                await self._redis.xgroup_create(dlq_key, "dlq-readers", id="0", mkstream=True)
        logger.info("Purged %d DLQ messages", length)
        return length

    async def reclaim_stale(self) -> int:
        """Reclaim messages that have been pending longer than reclaim_idle_ms."""
        try:
            result = await self._redis.xautoclaim(
                self._config.stream_key,
                self._config.consumer_group,
                self._consumer_name,
                min_idle_time=self._config.reclaim_idle_ms,
                start_id="0-0",
                count=10,
            )
            # result is (next_start_id, claimed_messages, deleted_ids)
            claimed = result[1] if len(result) > 1 else []
            if claimed:
                logger.info("Reclaimed %d stale messages", len(claimed))
            return len(claimed)
        except Exception as e:
            logger.warning("XAUTOCLAIM failed: %s", e)
            return 0

    async def reset_idle(self, message_id: str) -> None:
        """Reset idle time for a message by re-claiming it for the current consumer.

        This prevents XAUTOCLAIM from stealing a message that is still being
        actively processed (heartbeat keeps it alive).
        """
        try:
            await self._redis.xclaim(
                self._config.stream_key,
                self._config.consumer_group,
                self._consumer_name,
                min_idle_time=0,
                message_ids=[message_id],
            )
            logger.debug("Reset idle for msg=%s", message_id)
        except Exception as e:
            logger.warning("XCLAIM reset_idle failed for msg=%s: %s", message_id, e)
