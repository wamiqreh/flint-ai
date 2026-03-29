# 5-Minute Quickstart

Go from zero to running AI agent workflows in five steps. No .NET, no database, no Redis — just Docker and Python.

---

## Prerequisites

- **Docker** (Docker Desktop or Docker Engine)
- **Python 3.9+** (for the SDK)

---

## Step 1 — Start the Server

One command. This starts the orchestrator in dev mode with an in-memory queue and store — no external dependencies.

```bash
docker compose -f docker-compose.dev.yml up -d
```

Verify it's running:

```bash
curl http://localhost:5156/health
# → Healthy
```

!!! tip "What's happening?"
    The `docker-compose.dev.yml` file runs the orchestrator with `USE_INMEMORY_QUEUE=true` and no database connection — everything is in-memory. Perfect for development. For production, switch to the main `docker-compose.yml` which adds Redis and PostgreSQL.

---

## Step 2 — Install the Python SDK

```bash
pip install flint-ai
```

This gives you a Python client and type-safe models. Want the CLI too?

```bash
pip install "flint-ai[cli]"
```

---

## Step 3 — Submit Your First Task

Create a file called `hello.py`:

```python
from flint_ai import OrchestratorClient

# Connect to the local server
client = OrchestratorClient("http://localhost:5156")

# Submit a task to the "dummy" agent
task_id = client.submit_task("dummy", "Hello, world!")
print(f"Task submitted: {task_id}")

# Wait for the result
result = client.wait_for_task(task_id)
print(f"State: {result.state}")
print(f"Result: {result.result}")
```

Run it:

```bash
python hello.py
# Task submitted: 3fa85f64-5717-4562-b3fc-2c963f66afa6
# State: Succeeded
# Result: [dummy] processed prompt: Hello, world!
```

🎉 **You just ran your first agent task.**

!!! note "About the dummy agent"
    The `dummy` agent echoes your prompt back. It's built-in for testing. To use real AI, set `OPENAI_API_KEY`, `CLAUDE_API_KEY`, or `COPILOT_API_KEY` as environment variables on the server and use `"openai"`, `"claude"`, or `"copilot"` as the agent type.

---

## Step 4 — Check Task Status (curl)

You can also inspect tasks with plain HTTP:

```bash
# Submit
curl -s -X POST http://localhost:5156/tasks \
  -H "Content-Type: application/json" \
  -d '{"AgentType": "dummy", "Prompt": "echo test"}' | python -m json.tool

# Get result (replace with your task ID)
curl -s http://localhost:5156/tasks/{task_id} | python -m json.tool
```

Or use the CLI:

```bash
flint submit --agent dummy --prompt "hello from CLI"
# → prints task ID

flint status <task-id>
# → prints JSON with state, result, etc.
```

---

## Step 5 — Build a Workflow

Workflows chain multiple tasks into a pipeline (DAG). Here's a 3-node pipeline: generate → review → publish.

```python
from flint_ai import (
    OrchestratorClient,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
)

client = OrchestratorClient("http://localhost:5156")

# Define the workflow
workflow = WorkflowDefinition(
    Id="content-pipeline",
    Nodes=[
        WorkflowNode(
            Id="generate",
            AgentType="dummy",
            PromptTemplate="Write a blog post about AI agents",
            MaxRetries=3,
        ),
        WorkflowNode(
            Id="review",
            AgentType="dummy",
            PromptTemplate="Review this blog post for accuracy",
            HumanApproval=True,  # ← pauses for human approval!
        ),
        WorkflowNode(
            Id="publish",
            AgentType="dummy",
            PromptTemplate="Format and publish the blog post",
        ),
    ],
    Edges=[
        WorkflowEdge(FromNodeId="generate", ToNodeId="review"),
        WorkflowEdge(FromNodeId="review", ToNodeId="publish"),
    ],
)

# Create and start it
client.create_workflow(workflow)
client.start_workflow("content-pipeline")
print("Workflow started!")

# Check node states
nodes = client.get_workflow_nodes("content-pipeline")
for node in nodes:
    print(f"  {node['Id']}: {node.get('State', 'pending')}")
```

The `review` node has `HumanApproval=True`, so the workflow will pause there until someone approves:

```bash
# Approve the review step
curl -X POST http://localhost:5156/workflows/content-pipeline/nodes/review/approve

# Or reject it
curl -X POST http://localhost:5156/workflows/content-pipeline/nodes/review/reject
```

---

## Step 6 — Monitor

### Prometheus Metrics

```bash
curl http://localhost:5156/metrics
```

Exposes counters, gauges, and histograms for tasks, queues, and agents. Point your Prometheus scraper at this endpoint.

### Dashboard Endpoints

| Endpoint | What it shows |
|---|---|
| `GET /dashboard/agents/concurrency` | Per-agent concurrency limits and current usage |
| `GET /dashboard/workflows` | All workflow summaries |
| `GET /dashboard/dlq` | Dead-lettered tasks |
| `GET /dashboard/workflows/{id}/nodes` | Node states for a specific workflow |

### Live Streaming

Stream real-time task updates via SSE or WebSocket:

```bash
# SSE stream
curl -N http://localhost:5156/tasks/{task_id}/stream

# WebSocket
wscat -c ws://localhost:5156/tasks/{task_id}/ws
```

---

## What's Next?

- **[Python SDK Reference](python-sdk.md)** — Full API reference, async client, batch operations, workflow builder, error handling
- **[TypeScript SDK Reference](typescript-sdk.md)** — TypeScript client, streaming, workflow builder
- **[Architecture](architecture.md)** — How the queue, workers, and workflow engine work together
- **[Configuration](../docs/ENV_VARS.md)** — All environment variables (agent keys, queue backends, concurrency limits)

### Production Deployment

When you're ready to move past dev mode:

```bash
# Full stack: orchestrator + Redis + PostgreSQL
docker compose up -d
```

This gives you durable persistence (PostgreSQL) and production-grade queuing (Redis Streams) instead of in-memory stores.
