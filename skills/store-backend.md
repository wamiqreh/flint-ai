# Skill: Store Backend Development

Load when: adding new store backends, modifying persistence layer, integrating databases.

## Store Interfaces

`flint_ai/server/store/__init__.py` — Two abstract classes.

### BaseTaskStore (8 methods)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `create` | `async (record) -> None` | Persist new task |
| `get` | `async (task_id) -> TaskRecord \| None` | Retrieve by ID |
| `update` | `async (record) -> None` | Update existing |
| `compare_and_swap` | `async (task_id, expected, record) -> bool` | **Atomic CAS** |
| `update_state` | `async (task_id, state, **kwargs) -> bool` | Update state + fields |
| `list_tasks` | `async (state, workflow_id, limit, offset) -> list` | List with filters |
| `count_by_state` | `async () -> dict[str, int]` | Count grouped by state |
| `connect` / `disconnect` | `async () -> None` | Lifecycle |

### BaseWorkflowStore (8 methods)

| Method | Signature | Purpose |
|--------|-----------|---------|
| `save_definition` | `async (definition) -> None` | Save workflow def |
| `get_definition` | `async (workflow_id) -> WorkflowDefinition \| None` | Get definition |
| `list_definitions` | `async (limit) -> list` | List all definitions |
| `delete_definition` | `async (workflow_id) -> None` | Delete definition |
| `create_run` | `async (run) -> None` | Create run instance |
| `get_run` | `async (run_id) -> WorkflowRun \| None` | Get run |
| `update_run` | `async (run) -> None` | Update run |
| `list_runs` | `async (workflow_id, limit) -> list` | List runs |
| `list_running_runs` | `async () -> list` | For crash recovery |

## CRITICAL: compare_and_swap

This is the core concurrency primitive. It MUST be atomic.

**WRONG (race condition):**
```python
async def compare_and_swap(self, task_id, expected, record):
    current = await self.get(task_id)
    if current.state == expected:
        await self.update(record)
        return True
    return False
```

**RIGHT (atomic):**
```python
# Postgres example
async def compare_and_swap(self, task_id, expected, record):
    result = await self.pool.execute(
        "UPDATE tasks SET state=$1, ... WHERE id=$2 AND state=$3",
        record.state, task_id, expected
    )
    return result == "UPDATE 1"
```

## Creating a New Backend

### 1. File location
`flint_ai/server/store/{backend_name}.py`

### 2. Template
```python
from flint_ai.server.store import BaseTaskStore, BaseWorkflowStore
from flint_ai.server.engine import TaskRecord

class MyTaskStore(BaseTaskStore):
    def __init__(self, url: str):
        self.url = url

    async def connect(self):
        ...

    async def disconnect(self):
        ...

    async def create(self, record: TaskRecord) -> None:
        ...

    async def get(self, task_id: str) -> TaskRecord | None:
        ...

    async def update(self, record: TaskRecord) -> None:
        ...

    async def compare_and_swap(self, task_id: str, expected_state, record: TaskRecord) -> bool:
        # MUST be atomic
        ...

    async def update_state(self, task_id: str, state, **kwargs) -> bool:
        ...

    async def list_tasks(self, state=None, workflow_id=None, limit=100, offset=0) -> list[TaskRecord]:
        ...

    async def count_by_state(self) -> dict[str, int]:
        ...


class MyWorkflowStore(BaseWorkflowStore):
    def __init__(self, url: str):
        self.url = url

    async def connect(self):
        ...

    async def disconnect(self):
        ...

    async def save_definition(self, definition) -> None:
        ...

    async def get_definition(self, workflow_id: str):
        ...

    async def list_definitions(self, limit: int = 100):
        ...

    async def delete_definition(self, workflow_id: str) -> None:
        ...

    async def create_run(self, run) -> None:
        ...

    async def get_run(self, run_id: str):
        ...

    async def update_run(self, run) -> None:
        ...

    async def list_runs(self, workflow_id: str | None = None, limit: int = 100):
        ...

    async def list_running_runs(self) -> list:
        ...
```

### 3. Register in config
Add to `StoreBackend` enum in `flint_ai/server/config.py`:
```python
class StoreBackend(Enum):
    MEMORY = "memory"
    POSTGRES = "postgres"
    MY_BACKEND = "my_backend"  # Add this
```

### 4. Add factory + auto-detection
```python
if "MY_DB_URL" in os.environ:
    return StoreBackend.MY_BACKEND
```

## Reference Implementations

| File | Complexity | Key patterns |
|------|------------|--------------|
| `store/memory.py` | Simple | Dict-backed, deep copies for safety |
| `store/postgres.py` | Complex | `asyncpg` pool, migrations, atomic CAS, column whitelist |

## Postgres Migration Pattern

If your backend needs schema migrations:
```python
MIGRATIONS = [
    "CREATE TABLE IF NOT EXISTS tasks (...)",
    "CREATE TABLE IF NOT EXISTS workflow_definitions (...)",
    "CREATE TABLE IF NOT EXISTS workflow_runs (...)",
    "CREATE TABLE IF NOT EXISTS schema_version (version INT)",
]
```

## Key Details

- InMemory store uses `copy.deepcopy()` to prevent mutation bugs
- Postgres uses column whitelist to prevent SQL injection in `update_state`
- `list_running_runs()` is used for crash recovery on startup
- TaskRecord is a Pydantic model — serialize/deserialize carefully

## Testing

```python
@pytest.fixture
async def my_store():
    store = MyTaskStore(url="...")
    await store.connect()
    yield store
    await store.disconnect()

async def test_cas_atomic(my_store):
    # Two concurrent CAS on same task — only one should succeed
    ...
```

Test: CRUD, CAS atomicity, concurrent writes, isolation, crash recovery.
