<div align="center">

# 🔥 Flint AI

**Fault-tolerant AI agent orchestration. Build → Queue → Retry → Observe.**

[![PyPI](https://img.shields.io/pypi/v/flint-ai?style=flat-square&color=orange)](https://pypi.org/project/flint-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-279%20passed-brightgreen?style=flat-square)]()

*Production-grade task queues, DAG workflows, and a live dashboard — in 20 lines of Python. Your API keys never leave your machine.*

</div>

---

## Quick Start

```bash
pip install flint-ai[openai]
export OPENAI_API_KEY=sk-...
```

```python
from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(name="researcher", model="gpt-4o-mini",
    instructions="Research the topic. Return key findings.")
writer = FlintOpenAIAgent(name="writer", model="gpt-4o-mini",
    instructions="Write a polished summary from the research.")

results = (
    Workflow("research-pipeline")
    .add(Node("research", agent=researcher, prompt="AI orchestration 2025"))
    .add(Node("write", agent=writer, prompt="Summarize the research").depends_on("research"))
    .run()  # Zero setup — engine starts in-process
)

print(results["research"])   # {"findings": [...]}
print(results["write"])      # "Executive summary: ..."
# → Dashboard: http://localhost:5160/ui/
```

Costs auto-track. Failures auto-retry. Dead agents go to DLQ. Everything is queryable.

---

## What Flint Solves

| Problem | Flint |
|---------|-------|
| Agent fails mid-pipeline | Auto-retry with exponential backoff |
| Keeps failing forever | Dead Letter Queue — query, inspect, retry from dashboard |
| Worker crashes | DB heartbeat + stale task recovery → auto-requeue |
| Server restarts | Agents auto-reconstruct from persistent config |
| Both server + client crash | Startup recovery re-queues failed tasks |
| Human must approve a step | Approval gates pause the DAG |
| Pass data between agents | Upstream output auto-flows to downstream prompt |
| See what's happening | Live dashboard with costs, traces, and DAG visualization |
| Scale beyond one machine | Redis queues, Postgres store, AWS SQS — all interchangeable |
| Keep API keys on your machine | Client-worker pattern — server orchestrates, agents run on **your** PC |

### vs. Alternatives

| | LangGraph | CrewAI | Temporal | **Flint** |
|--|-----------|--------|----------|-----------|
| Retry + DLQ | ❌ | ❌ | ✅ | ✅ |
| Crash recovery | ❌ | ❌ | ✅ | ✅ |
| Live dashboard | ❌ | ❌ | Paid | ✅ Free |
| API keys on client | — | — | ❌ Server holds keys | ✅ Your machine |
| Install | Complex | pip | Heavy infra | `pip install` |
| Lines to first pipeline | 50+ | 40+ | 200+ | **20** |

---

## Three Run Modes, Same Code

### 1. Hangfire Mode — Start Once, Enqueue Anywhere

Register at app startup. Call `workflow.run()` from **anywhere** — no engine param needed.

```python
# ── main.py (or FastAPI lifespan) ────────────────────────────
from flint_ai import configure_engine, shutdown_engine
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(name="researcher", model="gpt-4o-mini")
writer = FlintOpenAIAgent(name="writer", model="gpt-4o-mini")

configure_engine(agents=[researcher, writer], port=5160, workers=4)
# Background engine started. Workers polling. Dashboard live.

# ── endpoints/user_routes.py ─────────────────────────────────
from flint_ai import Workflow, Node

results = (
    Workflow("user-request")
    .add(Node("research", agent=researcher, prompt=request.input))
    .add(Node("write", agent=writer).depends_on("research"))
    .run()  # ← Auto-discovers global engine. Zero boilerplate.
)

# ── endpoints/admin_routes.py ────────────────────────────────
# Another workflow, same engine, same queue
results = Workflow("admin-task").add(Node("step", agent=researcher)).run()

# ── app shutdown ─────────────────────────────────────────────
shutdown_engine()
```

This is the **recommended pattern** for production apps. One engine, many workflows, shared queue/dashboard/costs.

### 2. Embedded — Quick Scripts & Testing

Engine starts and stops per call. Good for one-offs, bad for apps.

```python
results = workflow.run()  # Start engine → run → stop
# Dashboard at http://localhost:5160/ui/
```

### 3. Server + Worker — Distributed Production

```bash
# Terminal 1: server (dashboard, queue, DAG engine)
docker compose up -d
```

```python
# Terminal 2: your code — agents run HERE, server orchestrates
results = workflow.run(server_url="http://localhost:5156")
```

The FlintWorker claims tasks from the server, executes agents on your machine, reports results back. **API keys never leave your machine.**

---

## Crash-Proof Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Python App                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  main.py (startup)                                  │   │
│  │                                                     │   │
│  │  configure_engine(agents=[...])                     │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │  Global FlintEngine (singleton)              │  │   │
│  │  │  • FastAPI server on :5160                   │  │   │
│  │  │  • Worker pool (polling queue)               │  │   │
│  │  │  • Shared queue + store + dashboard          │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ endpoint A   │  │ endpoint B   │  │ endpoint C   │     │
│  │ workflow.run()│  │ workflow.run()│  │ workflow.run()│     │
│  │ (auto-discovers global engine)  │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

**What survives what:**

| Crash Scenario | What Happens | Recovery |
|---------------|--------------|----------|
| Worker dies mid-execution | DB heartbeat stops | Stale task detected → auto-requeued to another worker |
| Server restarts | In-memory state lost | Agents auto-reconstruct from DB config, failed tasks re-queued |
| Both crash | Everything down | On startup: all non-terminal tasks restored, workers reclaim |
| Queue backend dies | Tasks in-flight lost | PostgreSQL preserves all task records, re-enqueue on restart |

---

## Cost Tracking — Zero Boiler

Cost tracking is **enabled by default**. No manual tracker needed:

```python
from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

# That's it. Cost is auto-tracked.
agent = FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini")

results = (
    Workflow("cost-demo")
    .add(Node("summarize", agent=agent, prompt="Summarize this article..."))
    .run()
)
# → View costs at http://localhost:5160/ui/costs
```

### Centralized Pricing

Pricing comes from the database (or defaults). Override per agent if needed:

```python
# Override pricing for this agent only
agent = FlintOpenAIAgent(name="expensive-agent", model="gpt-4o",
                         cost_config_override={"prompt": 30.0, "completion": 60.0})

# Or manage pricing centrally
from flint_ai.config import set_pricing
set_pricing("gpt-4o", {"prompt": 30.0, "completion": 60.0})

# Disable cost tracking entirely
agent = FlintOpenAIAgent(name="no-costs", model="gpt-4o-mini",
                         enable_cost_tracking=False)
```

---

## Dashboard

When running (embedded or server), explore:

| Page | What You See |
|------|-------------|
| [`/ui/`](http://localhost:5160/ui/) | Overview — queue lengths, recent runs |
| [`/ui/costs`](http://localhost:5160/ui/costs) | Cost by model, timeline, per-task breakdown |
| [`/ui/tools`](http://localhost:5160/ui/tools) | Tool execution tree, errors with stack traces |
| [`/ui/runs`](http://localhost:5160/ui/runs) | Workflow runs with DAG visualization |
| [`/docs`](http://localhost:5160/docs) | Swagger API — query tasks, retry DLQ, inspect state |

### Query Anything via API

```bash
# Get task details
curl http://localhost:5160/tasks/{task_id}

# Retry a dead-lettered task
curl -X POST http://localhost:5160/dashboard/dlq/{msg_id}/retry

# Get cost by workflow run
curl http://localhost:5160/dashboard/cost/workflow/{run_id}

# List all tool executions
curl http://localhost:5160/dashboard/tools/executions
```

---

## Quickstart Examples

| Example | What | Lines | API Key |
|---------|------|-------|---------|
| [01_hello_workflow](examples/quickstart/01_hello_workflow.py) | 3-node pipeline | 20 | None |
| [02_with_cost_tracking](examples/quickstart/02_with_cost_tracking.py) | Same + auto costs | 25 | OpenAI |
| [03_embedded_worker](examples/quickstart/03_embedded_worker.py) | Custom worker config | 22 | None |
| [04_approval_gates](examples/quickstart/04_approval_gates.py) | Human approval step | 28 | None |
| [05_parallel_branches](examples/quickstart/05_parallel_branches.py) | Fan-out / fan-in | 22 | None |

```bash
python examples/quickstart/01_hello_workflow.py
```

### Production Pattern (Hangfire Mode)

```python
# main.py — start once
from flint_ai import configure_engine, shutdown_engine
from flint_ai.adapters.openai import FlintOpenAIAgent

configure_engine(
    agents=[FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini")],
    port=5160, workers=4,
)

# endpoint1.py — from anywhere
from flint_ai import Workflow, Node
results = Workflow("task-1").add(
    Node("summarize", "summarizer", prompt="Summarize this...")
).run()  # Auto-uses global engine

# endpoint2.py — also works
results = Workflow("task-2").add(
    Node("step", "summarizer", prompt="Another task...")
).run()  # Same engine, same queue

# shutdown
shutdown_engine()
```

---

## Features

| Category | Details |
|----------|---------|
| **Workflows** | DAG execution, parallel branches, fan-out/fan-in, data passing |
| **Fault tolerance** | Retry with backoff, DLQ, stale task recovery, startup recovery |
| **Crash resilience** | DB heartbeat (Redis + SQS), auto-requeue, agent config persistence |
| **Human-in-the-loop** | Approval gates pause the DAG, approve/reject from code or dashboard |
| **Adapters** | OpenAI, Anthropic, LangChain, CrewAI — or `class MyAgent(FlintAdapter)` |
| **Queues** | Redis Streams, AWS SQS, in-memory (dev) — all interchangeable |
| **Store** | PostgreSQL (prod), in-memory (dev) — same schema, same behavior |
| **Observability** | Dashboard UI, cost tracking, tool logging, Prometheus metrics |
| **Security** | API key auth, CORS, input validation, correlation IDs |
| **Deployment** | Docker, Docker Compose, Kubernetes, Terraform (AWS) |

---

## Build Your Own Adapter

```python
from flint_ai import FlintAdapter, AgentRunResult

class MyAgent(FlintAdapter):
    name = "my-agent"

    async def run(self, input_data: dict) -> AgentRunResult:
        result = await call_my_llm(input_data["prompt"])
        return AgentRunResult(output=result, success=True)
```

Register it and it just works:

```python
results = (
    Workflow("my-pipeline")
    .add(Node("step", agent=MyAgent(), prompt="Do something"))
    .run()
)
```

---

## Install

```bash
# Core + OpenAI adapter
pip install flint-ai[openai]

# Core + Anthropic adapter
pip install flint-ai[anthropic]

# Full: both adapters + server + Postgres + Redis
pip install flint-ai[all]
```

---

## Run in Production

```bash
# docker-compose.yml — PostgreSQL + Redis + Server
docker compose up -d

# Monitor
docker compose logs -f flint-server
# Dashboard at http://localhost:5160/ui/
```

---

## License

[MIT](LICENSE)
