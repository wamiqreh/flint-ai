# Python SDK

The official Python client for Flint. Provides both async and sync clients, typed models, automatic retries, and a CLI.

---

## Installation

```bash
pip install flint-ai
```

### Optional Extras

```bash
# CLI (adds the `flint` command)
pip install "flint-ai[cli]"

# LangChain adapter
pip install "flint-ai[langchain]"

# Everything
pip install "flint-ai[cli,langchain]"
```

**Requirements:** Python 3.9+, httpx, pydantic v2

---

## Client Setup

### Async Client (recommended)

Use `AsyncOrchestratorClient` for production code, web servers, and anywhere you're already using `async/await`.

```python
from flint_ai import AsyncOrchestratorClient

# As a context manager (auto-closes connection)
async with AsyncOrchestratorClient("http://localhost:5156") as client:
    task_id = await client.submit_task("openai", "Summarize this")
    result = await client.wait_for_task(task_id)
    print(result.result)
```

```python
# Or manage the lifecycle yourself
client = AsyncOrchestratorClient("http://localhost:5156")
try:
    task_id = await client.submit_task("dummy", "Hello")
    result = await client.wait_for_task(task_id)
finally:
    await client.close()
```

### Sync Client

Use `OrchestratorClient` for scripts, notebooks, and CLIs where you don't want to deal with `asyncio`.

```python
from flint_ai import OrchestratorClient

client = OrchestratorClient("http://localhost:5156")
task_id = client.submit_task("dummy", "Hello")
result = client.wait_for_task(task_id)
print(result.state, result.result)
```

### Configuration

Both clients accept the same configuration options:

```python
client = AsyncOrchestratorClient(
    base_url="http://localhost:5156",
    connect_timeout=5.0,      # TCP connect timeout (seconds)
    read_timeout=30.0,        # Read timeout (seconds)
    write_timeout=30.0,       # Write timeout (seconds)
    max_retries=3,            # Retry count for transient errors (429, 502, 503, 504)
    backoff_base=0.5,         # Base delay for exponential backoff
    backoff_max=30.0,         # Maximum delay between retries
)
```

You can also pass a pre-built `httpx.Timeout` object:

```python
import httpx

client = AsyncOrchestratorClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
)
```

---

## Task Operations

### Submit a Task

```python
task_id = await client.submit_task(
    agent_type="openai",          # Which agent to use
    prompt="Write a haiku",       # The prompt
    workflow_id=None,             # Optional: attach to a workflow
)
# Returns: str (the task ID)
```

### Get Task Status

```python
from flint_ai import TaskResponse

task: TaskResponse = await client.get_task(task_id)
print(task.id)          # "3fa85f64-..."
print(task.state)       # "Pending" | "Queued" | "Running" | "Succeeded" | "Failed" | "DeadLetter"
print(task.result)      # Agent output (when succeeded)
print(task.workflow_id) # None or workflow ID
```

### Wait for Completion

Polls until the task reaches a terminal state (`Succeeded`, `Failed`, or `DeadLetter`):

```python
result = await client.wait_for_task(
    task_id,
    poll_interval_seconds=1.0,  # How often to poll (default: 1s)
)
if result.state == "Succeeded":
    print(result.result)
else:
    print(f"Task failed: {result.state}")
```

### Batch Submit

Submit multiple tasks in parallel:

```python
from flint_ai import TaskSubmission

tasks = [
    TaskSubmission(AgentType="openai", Prompt="Translate to French: Hello"),
    TaskSubmission(AgentType="openai", Prompt="Translate to Spanish: Hello"),
    TaskSubmission(AgentType="openai", Prompt="Translate to German: Hello"),
]

task_ids = await client.submit_tasks(tasks)
# Returns: ["id1", "id2", "id3"]

# Wait for all
import asyncio
results = await asyncio.gather(*[client.wait_for_task(tid) for tid in task_ids])
for r in results:
    print(r.result)
```

### Stream Task Updates (SSE)

Get real-time state changes as they happen:

```python
async for update in client.stream_task(task_id):
    print(f"State: {update.state}")
    if update.state == "Succeeded":
        print(f"Result: {update.result}")
        break
```

---

## Workflow Operations

Workflows let you chain tasks into directed acyclic graphs (DAGs) with retries, human approval gates, and conditional edges.

### Define a Workflow

```python
from flint_ai import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
)

workflow = WorkflowDefinition(
    Id="code-review-pipeline",
    Nodes=[
        WorkflowNode(
            Id="generate",
            AgentType="openai",
            PromptTemplate="Generate Python code for: {input}",
            MaxRetries=3,
            DeadLetterOnFailure=True,
        ),
        WorkflowNode(
            Id="lint",
            AgentType="openai",
            PromptTemplate="Lint and fix this code",
        ),
        WorkflowNode(
            Id="review",
            AgentType="openai",
            PromptTemplate="Code review this implementation",
            HumanApproval=True,  # Pauses for human approve/reject
        ),
    ],
    Edges=[
        WorkflowEdge(FromNodeId="generate", ToNodeId="lint"),
        WorkflowEdge(FromNodeId="lint", ToNodeId="review"),
    ],
)
```

### Create and Start

```python
# Register the workflow
await client.create_workflow(workflow)

# Start execution
await client.start_workflow("code-review-pipeline")
```

### List Workflows

```python
workflows = await client.list_workflows()
for wf in workflows:
    print(f"{wf.id}: {len(wf.nodes)} nodes, {len(wf.edges)} edges")
```

### Inspect Node States

```python
nodes = await client.get_workflow_nodes("code-review-pipeline")
for node in nodes:
    print(f"  {node['Id']}: {node.get('State', 'pending')}")
```

### Human Approval

When a workflow node has `HumanApproval=True`, it pauses and waits. Use HTTP to approve or reject:

```bash
# Approve
curl -X POST http://localhost:5156/workflows/code-review-pipeline/nodes/review/approve

# Reject
curl -X POST http://localhost:5156/workflows/code-review-pipeline/nodes/review/reject
```

### Workflow Builder Helper

You can build workflows programmatically using a helper pattern:

```python
def build_pipeline(
    workflow_id: str,
    steps: list[tuple[str, str, str]],  # (id, agent, prompt)
    human_approval_at: set[str] | None = None,
) -> WorkflowDefinition:
    """Build a simple linear pipeline from a list of steps."""
    human_approval_at = human_approval_at or set()
    nodes = [
        WorkflowNode(
            Id=step_id,
            AgentType=agent,
            PromptTemplate=prompt,
            HumanApproval=step_id in human_approval_at,
        )
        for step_id, agent, prompt in steps
    ]
    edges = [
        WorkflowEdge(FromNodeId=steps[i][0], ToNodeId=steps[i + 1][0])
        for i in range(len(steps) - 1)
    ]
    return WorkflowDefinition(Id=workflow_id, Nodes=nodes, Edges=edges)

# Usage
pipeline = build_pipeline(
    "my-pipeline",
    steps=[
        ("draft",   "openai", "Write a draft"),
        ("review",  "openai", "Review the draft"),
        ("publish", "openai", "Publish the final version"),
    ],
    human_approval_at={"review"},
)
```

---

## Error Handling

The SDK raises typed exceptions that you can catch individually:

```python
from flint_ai import (
    OrchestratorError,        # Base exception
    TaskNotFoundError,        # 404 — task/resource not found
    WorkflowValidationError,  # 422 — invalid workflow definition
    RateLimitError,           # 429 — rate limited
    AuthenticationError,      # 401/403 — auth failure
    ConnectionError,          # Cannot reach server
)

try:
    task = await client.get_task("nonexistent-id")
except TaskNotFoundError as e:
    print(f"Not found: {e} (status={e.status_code})")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except ConnectionError as e:
    print(f"Server unreachable: {e}")
except OrchestratorError as e:
    print(f"API error: {e} (status={e.status_code}, detail={e.detail})")
```

All exceptions inherit from `OrchestratorError` and carry:

- `status_code` — HTTP status code (if applicable)
- `detail` — Raw response body from the server

### Automatic Retries

The client automatically retries on transient errors (HTTP 429, 502, 503, 504) and connection failures. Retries use exponential backoff with full jitter. If a `Retry-After` header is present, the client respects it.

You can configure retry behavior:

```python
client = AsyncOrchestratorClient(
    max_retries=5,       # Increase from default 3
    backoff_base=1.0,    # Start with 1s delay
    backoff_max=60.0,    # Cap at 60s
)
```

---

## LangChain Adapter

Plug the orchestrator into LangChain as a runnable:

```python
from flint_ai import (
    AsyncOrchestratorClient,
    LangChainOrchestratorRunnable,
)

client = AsyncOrchestratorClient()
runnable = LangChainOrchestratorRunnable(
    client=client,
    agent_type="openai",
)

# Use it like any LangChain runnable
result = await runnable.ainvoke("Explain quantum computing")
print(result.state, result.result)
```

Install the LangChain extra:

```bash
pip install "flint-ai[langchain]"
```

---

## Monitoring

### Stream Prometheus Metrics

```python
async for snapshot in client.stream_metrics(interval_seconds=5.0):
    print(snapshot)  # Raw Prometheus text format
```

### Dashboard Endpoints

Query dashboard data via HTTP:

```python
import httpx

# Agent concurrency
resp = httpx.get("http://localhost:5156/dashboard/agents/concurrency")
print(resp.json())

# Workflow summaries
resp = httpx.get("http://localhost:5156/dashboard/workflows")
print(resp.json())

# Dead-letter queue
resp = httpx.get("http://localhost:5156/dashboard/dlq")
print(resp.json())
```

---

## CLI Reference

Install with:

```bash
pip install "flint-ai[cli]"
```

### Submit a Task

```bash
flint submit --agent openai --prompt "Write a haiku about coding"
# → prints task ID

flint submit -a dummy -p "Quick test"
# → short flags work too
```

### Check Task Status

```bash
flint status <task-id>
# → prints JSON: { "id": "...", "state": "Succeeded", "result": "..." }
```

### Workflow Commands

```bash
# List all workflows
flint workflows list

# Start a workflow
flint workflows start <workflow-id>
```

### Custom Server URL

All commands support `--base-url`:

```bash
flint submit --agent dummy --prompt "hello" --base-url http://staging:5156
```

---

## Models Reference

### TaskResponse

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Task ID |
| `state` | `str` | `Pending`, `Queued`, `Running`, `Succeeded`, `Failed`, `DeadLetter` |
| `result` | `str | None` | Agent output (populated on success) |
| `workflow_id` | `str | None` | Workflow this task belongs to |

### WorkflowNode

| Field | Type | Default | Description |
|---|---|---|---|
| `Id` | `str` | required | Unique node identifier |
| `AgentType` | `str` | required | Agent to execute this node |
| `PromptTemplate` | `str` | required | Prompt sent to the agent |
| `MaxRetries` | `int` | `3` | Max retry attempts |
| `DeadLetterOnFailure` | `bool` | `True` | Send to DLQ on final failure |
| `HumanApproval` | `bool` | `False` | Pause for approval before executing |

### WorkflowEdge

| Field | Type | Default | Description |
|---|---|---|---|
| `FromNodeId` | `str` | required | Source node |
| `ToNodeId` | `str` | required | Target node |
| `Condition` | `str` | `""` | Optional condition expression |

### WorkflowDefinition

| Field | Type | Description |
|---|---|---|
| `Id` | `str` | Unique workflow identifier |
| `Nodes` | `list[WorkflowNode]` | Nodes in the DAG |
| `Edges` | `list[WorkflowEdge]` | Edges connecting nodes |
