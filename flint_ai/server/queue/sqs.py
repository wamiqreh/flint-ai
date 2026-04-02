"""AWS SQS queue adapter with DLQ support.

Uses boto3/aioboto3 for async SQS operations. Supports standard and
FIFO queues, visibility timeout, long-polling, and dead-letter queues.

Install: pip install flint-ai[sqs] or pip install aioboto3
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from flint_ai.server.config import SQSConfig
from flint_ai.server.queue import BaseQueue, QueueMessage

logger = logging.getLogger("flint.server.queue.sqs")


class SQSQueue(BaseQueue):
    """Production queue using AWS SQS.

    Features:
    - Long-polling for efficient message retrieval
    - Visibility timeout for at-least-once delivery
    - Native DLQ via SQS redrive policy (or manual DLQ queue)
    - Message attributes for metadata
    """

    def __init__(self, config: SQSConfig) -> None:
        self._config = config
        self._session: Any = None
        self._client: Any = None
        # In-flight messages: receipt_handle → message data (for ack/nack)
        self._in_flight: Dict[str, Dict[str, Any]] = {}

    async def connect(self) -> None:
        try:
            import aioboto3
        except ImportError:
            raise ImportError(
                "aioboto3 required for SQS queue. "
                "Install with: pip install flint-ai[sqs] or pip install aioboto3"
            )

        self._session = aioboto3.Session()
        self._client = await self._session.client(
            "sqs",
            region_name=self._config.region,
        ).__aenter__()
        logger.info("Connected to SQS queue: %s", self._config.queue_url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def enqueue(self, task_id: str, data: Dict[str, Any], priority: int = 0) -> str:
        message_id = str(uuid.uuid4())
        body = json.dumps({
            "message_id": message_id,
            "task_id": task_id,
            "data": data,
            "priority": priority,
        })

        kwargs: Dict[str, Any] = {
            "QueueUrl": self._config.queue_url,
            "MessageBody": body,
            "MessageAttributes": {
                "task_id": {"StringValue": task_id, "DataType": "String"},
                "priority": {"StringValue": str(priority), "DataType": "Number"},
            },
        }

        # FIFO queues require MessageGroupId
        if self._config.queue_url.endswith(".fifo"):
            kwargs["MessageGroupId"] = data.get("agent_type", "default")
            kwargs["MessageDeduplicationId"] = message_id

        resp = await self._client.send_message(**kwargs)
        sqs_id = resp["MessageId"]
        logger.debug("Enqueued task %s → SQS message %s", task_id, sqs_id)
        return message_id

    async def dequeue(self, count: int = 1, block_ms: int = 5000) -> List[QueueMessage]:
        wait_seconds = min(block_ms // 1000, self._config.wait_time_seconds)

        resp = await self._client.receive_message(
            QueueUrl=self._config.queue_url,
            MaxNumberOfMessages=min(count, 10),  # SQS max is 10
            WaitTimeSeconds=wait_seconds,
            VisibilityTimeout=self._config.visibility_timeout,
            MessageAttributeNames=["All"],
        )

        messages = []
        for msg in resp.get("Messages", []):
            try:
                body = json.loads(msg["Body"])
                receipt = msg["ReceiptHandle"]
                task_id = body.get("task_id", "")
                data = body.get("data", {})
                attempt = data.get("attempt", 0)

                # Store receipt handle for ack/nack
                mid = body.get("message_id", msg["MessageId"])
                self._in_flight[mid] = {
                    "receipt_handle": receipt,
                    "body": body,
                }

                messages.append(QueueMessage(
                    message_id=mid,
                    task_id=task_id,
                    data=data,
                    attempt=attempt,
                ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.error("Failed to parse SQS message: %s", e)

        return messages

    async def ack(self, message_id: str) -> None:
        info = self._in_flight.pop(message_id, None)
        if not info:
            logger.warning("Cannot ack unknown message %s", message_id)
            return
        await self._client.delete_message(
            QueueUrl=self._config.queue_url,
            ReceiptHandle=info["receipt_handle"],
        )

    async def nack(self, message_id: str) -> None:
        info = self._in_flight.pop(message_id, None)
        if not info:
            return
        # Make message visible immediately for redelivery
        await self._client.change_message_visibility(
            QueueUrl=self._config.queue_url,
            ReceiptHandle=info["receipt_handle"],
            VisibilityTimeout=0,
        )

    async def move_to_dlq(self, message_id: str, reason: str = "") -> None:
        info = self._in_flight.pop(message_id, None)
        if not info:
            logger.warning("Cannot DLQ unknown message %s", message_id)
            return

        # Send to dedicated DLQ if configured
        if self._config.dlq_url:
            body = info["body"]
            body["dlq_reason"] = reason
            await self._client.send_message(
                QueueUrl=self._config.dlq_url,
                MessageBody=json.dumps(body),
            )

        # Delete from main queue
        await self._client.delete_message(
            QueueUrl=self._config.queue_url,
            ReceiptHandle=info["receipt_handle"],
        )
        logger.info("Moved message %s to DLQ: %s", message_id, reason)

    async def get_queue_length(self) -> int:
        resp = await self._client.get_queue_attributes(
            QueueUrl=self._config.queue_url,
            AttributeNames=["ApproximateNumberOfMessages"],
        )
        return int(resp["Attributes"].get("ApproximateNumberOfMessages", 0))

    async def get_dlq_length(self) -> int:
        if not self._config.dlq_url:
            return 0
        resp = await self._client.get_queue_attributes(
            QueueUrl=self._config.dlq_url,
            AttributeNames=["ApproximateNumberOfMessages"],
        )
        return int(resp["Attributes"].get("ApproximateNumberOfMessages", 0))

    async def get_dlq_messages(self, count: int = 50) -> List[QueueMessage]:
        if not self._config.dlq_url:
            return []

        messages = []
        resp = await self._client.receive_message(
            QueueUrl=self._config.dlq_url,
            MaxNumberOfMessages=min(count, 10),
            VisibilityTimeout=0,  # Peek only
        )
        for msg in resp.get("Messages", []):
            try:
                body = json.loads(msg["Body"])
                messages.append(QueueMessage(
                    message_id=body.get("message_id", msg["MessageId"]),
                    task_id=body.get("task_id", ""),
                    data=body,
                ))
            except (json.JSONDecodeError, KeyError):
                pass
        return messages

    async def retry_dlq_message(self, message_id: str) -> str:
        if not self._config.dlq_url:
            raise KeyError("No DLQ configured")

        # Read messages from DLQ to find the one to retry
        resp = await self._client.receive_message(
            QueueUrl=self._config.dlq_url,
            MaxNumberOfMessages=10,
            VisibilityTimeout=30,
        )
        for msg in resp.get("Messages", []):
            body = json.loads(msg["Body"])
            if body.get("message_id") == message_id:
                # Re-enqueue to main queue
                new_id = await self.enqueue(
                    task_id=body.get("task_id", ""),
                    data=body.get("data", {}),
                )
                # Delete from DLQ
                await self._client.delete_message(
                    QueueUrl=self._config.dlq_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
                return new_id

        raise KeyError(f"DLQ message {message_id} not found")

    async def purge_dlq(self) -> int:
        if not self._config.dlq_url:
            return 0
        count = await self.get_dlq_length()
        await self._client.purge_queue(QueueUrl=self._config.dlq_url)
        return count
