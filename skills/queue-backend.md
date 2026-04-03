# Skill: Queue Backend Development

Load when: adding new queue backends, modifying queue system, integrating message brokers.

## Queue Interface

`flint_ai/server/queue/__init__.py` — `BaseQueue` abstract class (12 methods).

## Required Methods

| Method | Signature | Purpose |
|--------|-----------|---------|
| `enqueue` | `async (task_id, data, priority) -> str` | Add task, return message ID |
| `dequeue` | `async (count, block_ms) -> list[QueueMessage]` | Fetch messages, optional block |
| `ack` | `async (message_id) -> None` | Acknowledge processing |
| `nack` | `async (message_id) -> None` | Negative ack, re-queue |
| `move_to_dlq` | `async (message_id, reason) -> None` | Move to dead-letter queue |
| `get_queue_length` | `async () -> int` | Pending count |
| `get_dlq_length` | `async () -> int` | DLQ count |
| `get_dlq_messages` | `async (count) -> list` | Peek DLQ |
| `retry_dlq_message` | `async (message_id) -> None` | Re-enqueue DLQ message |
| `purge_dlq` | `async () -> None` | Delete all DLQ |
| `connect` | `async () -> None` | Lifecycle |
| `disconnect` | `async () -> None` | Lifecycle |

## Optional Methods (override for performance)

| Method | Purpose |
|--------|---------|
| `reclaim_stale` | Reclaim messages idle too long |
| `reset_idle` | Update idle timestamp (heartbeat) |

## Creating a New Backend

### 1. File location
`flint_ai/server/queue/{backend_name}.py`

### 2. Template
```python
from flint_ai.server.queue import BaseQueue, QueueMessage

class MyQueue(BaseQueue):
    def __init__(self, url: str):
        self.url = url
        self._connected = False

    async def connect(self):
        # Initialize connection
        self._connected = True

    async def disconnect(self):
        # Cleanup
        self._connected = False

    async def enqueue(self, task_id: str, data: dict, priority: int = 0) -> str:
        # Add to queue, return message ID
        ...

    async def dequeue(self, count: int = 1, block_ms: int = 0) -> list[QueueMessage]:
        # Fetch messages
        ...

    async def ack(self, message_id: str) -> None:
        ...

    async def nack(self, message_id: str) -> None:
        ...

    async def move_to_dlq(self, message_id: str, reason: str) -> None:
        # Read original message, write to DLQ, delete from main
        ...

    async def get_queue_length(self) -> int:
        ...

    async def get_dlq_length(self) -> int:
        ...

    async def get_dlq_messages(self, count: int = 10) -> list:
        ...

    async def retry_dlq_message(self, message_id: str) -> None:
        # Read from DLQ, re-enqueue to main, delete from DLQ
        ...

    async def purge_dlq(self) -> None:
        ...
```

### 3. Register in config
Add to `QueueBackend` enum in `flint_ai/server/config.py`:
```python
class QueueBackend(Enum):
    MEMORY = "memory"
    REDIS = "redis"
    SQS = "sqs"
    MY_BACKEND = "my_backend"  # Add this
```

### 4. Add factory
In `create_queue()` function:
```python
if backend == QueueBackend.MY_BACKEND:
    return MyQueue(url=os.environ["MY_QUEUE_URL"])
```

### 5. Add auto-detection
```python
if "MY_QUEUE_URL" in os.environ:
    return QueueBackend.MY_BACKEND
```

## Reference Implementations

| File | Complexity | Key patterns |
|------|------------|--------------|
| `queue/memory.py` | Simple | `asyncio.Queue`, volatile, dev only |
| `queue/redis_streams.py` | Medium | Consumer groups, XAUTOCLAIM, dedicated DLQ stream |
| `queue/sqs.py` | Medium | `aioboto3`, long-polling, FIFO, visibility timeout |

## Key Details

- `QueueMessage` uses `__slots__` for memory efficiency
- Message ID must be unique string
- `dequeue` should respect `block_ms` (0 = non-blocking)
- DLQ must preserve original message data + add `dlq_reason`
- `retry_dlq_message` must strip DLQ metadata before re-enqueue

## Testing

Add to `tests/test_production_hardening.py` or create new test file:
```python
@pytest.fixture
async def my_queue():
    q = MyQueue(url="...")
    await q.connect()
    yield q
    await q.disconnect()
```

Test: enqueue→dequeue→ack, nack re-queue, DLQ flow, stale reclaim, concurrent access.
