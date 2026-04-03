# Skill: Testing

Load when: writing tests, adding test coverage, creating mocks, debugging test failures.

## Framework

pytest + pytest-asyncio. Config in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

## Test Files

| File | What it tests | Lines |
|------|--------------|-------|
| `tests/test_server.py` | Server models, in-memory queue/store, concurrency, DAG conditions, DAG engine, agents, config, metrics | 562 |
| `tests/test_adapters.py` | Adapter core types, base adapter, registry, tool decorator, FlintOpenAIAgent, workflow builder, failure paths | 361 |
| `tests/test_integration.py` | Mocked OpenAI agent, multi-tool rounds, full workflow, tool schema, registry + worker | 328 |
| `tests/test_e2e.py` | Task lifecycle, workflow DAG, circuit breaker, input validation, correlation ID, error action, client-worker | 897 |
| `tests/test_production_hardening.py` | CAS, concurrent claim races, distributed concurrency, scheduler leader election, Redis Pub/Sub, DAG recovery, logging, idempotency | 860 |

## Running Tests

```bash
pytest tests/ -v                    # All tests
pytest tests/test_server.py -v      # Single file
pytest tests/test_server.py::TestTaskEngine::test_submit_task -v  # Single test
pytest tests/ -v --cov=flint_ai     # With coverage
pytest tests/ -v -k "dag"           # Filter by name
```

## Common Fixtures

### Engine Stack (full in-memory)
```python
@pytest.fixture
async def engine_stack():
    queue = InMemoryQueue()
    store = InMemoryTaskStore()
    wf_store = InMemoryWorkflowStore()
    engine = TaskEngine(queue=queue, store=store, wf_store=wf_store)
    await queue.connect()
    await store.connect()
    yield engine
    await queue.disconnect()
    await store.disconnect()
```

### Mock Agents
```python
class EchoAgent(BaseAgent):
    @property
    def agent_type(self) -> str:
        return "echo"

    async def execute(self, prompt: str, **kwargs) -> str:
        return f"echo: {prompt}"

class FailingAgent(BaseAgent):
    @property
    def agent_type(self) -> str:
        return "failing"

    async def execute(self, prompt: str, **kwargs) -> str:
        raise RuntimeError("intentional failure")

class SlowAgent(BaseAgent):
    @property
    def agent_type(self) -> str:
        return "slow"

    async def execute(self, prompt: str, **kwargs) -> str:
        await asyncio.sleep(1.0)
        return "done"
```

### Mock Adapter (SDK-side)
```python
class MockAdapter(FlintAdapter):
    async def run(self, input_data: dict) -> AgentRunResult:
        return AgentRunResult(
            output=f"echo: {input_data['prompt']}",
            success=True,
        )
```

### Registry Clearing
```python
def setup_method(self):
    AdapterRegistry._adapters.clear()
```

## Test Patterns

### Task Lifecycle
```python
async def test_task_lifecycle(engine_stack):
    engine = engine_stack
    task_id = await engine.submit_task(
        agent_type="echo",
        prompt="hello",
        workflow_id=None,
    )
    task = await engine.claim_task(worker_id="w1", agent_types=["echo"])
    assert task.task_id == task_id
    await engine.report_result(task_id, success=True, output="world")
    record = await engine.store.get(task_id)
    assert record.state == TaskState.SUCCEEDED
```

### DAG Execution
```python
async def test_dag_execution(engine_stack):
    dag = DAG(
        nodes={
            "a": WorkflowNode(id="a", agent_type="echo"),
            "b": WorkflowNode(id="b", agent_type="echo"),
        },
        edges=[Edge("a", "b")],
    )
    run = await engine_stack.dag_engine.start_workflow(dag)
    # Process tasks and verify order
```

### Concurrent Claim Race
```python
async def test_concurrent_claim_race(engine_stack):
    # Submit one task, have two workers try to claim simultaneously
    # Only one should succeed (CAS)
    task_id = await engine_stack.submit_task(...)
    results = await asyncio.gather(
        engine_stack.claim_task(worker_id="w1", agent_types=["echo"]),
        engine_stack.claim_task(worker_id="w2", agent_types=["echo"]),
    )
    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1
```

### Mocked OpenAI
```python
@pytest.fixture
def mock_openai():
    with patch("openai.AsyncOpenAI") as MockClient:
        client = MockClient.return_value
        client.chat.completions.create.return_value = MockResponse(
            choices=[MockChoice(message=MockMessage(content="mocked response"))]
        )
        yield client
```

## Adding Tests for New Features

1. **New queue backend:** Add to `tests/test_production_hardening.py` or create `tests/test_queue_{backend}.py`
2. **New store backend:** Same pattern, test CRUD + CAS atomicity + concurrent writes
3. **New adapter:** Add to `tests/test_adapters.py`
4. **New DAG feature:** Add to `tests/test_server.py` or `tests/test_e2e.py`

## Coverage

```bash
pytest tests/ -v --cov=flint_ai --cov-report=html
# Open htmlcov/index.html
```

## Important

- Use `setup_method` for test isolation (clear registries, reset state)
- Async fixtures use `@pytest_asyncio.fixture`
- `asyncio_mode = "auto"` means all async functions are auto-wrapped
- InMemory store uses `copy.deepcopy()` — mutations don't leak between tests
- Always clean up connections in fixture teardown
