# Architecture

How Flint works under the hood. You don't need to know this to use the SDK — but it helps when debugging, tuning, or contributing.

---

## The Big Picture

```
┌────────────────────────────────────────────────────────────┐
│  Your Code  (Python SDK · TypeScript SDK · HTTP · CLI)     │
└──────────────────────┬─────────────────────────────────────┘
                       │  POST /tasks, POST /workflows
                       ▼
┌────────────────────────────────────────────────────────────┐
│  HTTP API  (ASP.NET Core — runs inside the Docker image)   │
│   • Task submission & status endpoints                     │
│   • Workflow CRUD & execution endpoints                    │
│   • Prometheus /metrics  •  Dashboard endpoints            │
└──────────────────────┬─────────────────────────────────────┘
                       │  Enqueue
                       ▼
┌────────────────────────────────────────────────────────────┐
│  Queue Layer                                               │
│   • In-Memory  (dev mode — zero dependencies)              │
│   • Redis Streams  (production — durable, auto-claim)      │
│   • Kafka / SQS  (adapter placeholders)                    │
└──────────────────────┬─────────────────────────────────────┘
                       │  Dequeue
                       ▼
┌────────────────────────────────────────────────────────────┐
│  Worker                                                    │
│   • Picks up tasks from the queue                          │
│   • Acquires per-agent concurrency semaphore               │
│   • Executes the agent (OpenAI, Claude, Copilot, custom)   │
│   • Retries with exponential backoff + jitter              │
│   • Saves result → releases semaphore                      │
│   • Notifies workflow engine if part of a DAG              │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│  Workflow Engine  (DAG Orchestration)                       │
│   • On success → enqueue downstream nodes                  │
│   • On failure → retry or dead-letter                      │
│   • Human approval gates (approve/reject via HTTP)         │
└────────────────────────────────────────────────────────────┘
```

---

## Task Lifecycle

Every task follows this state machine:

```
Pending → Queued → Running → Succeeded
                          └→ Failed → Retry (back to Queued)
                                   └→ DeadLetter (max retries exceeded)
```

| State | Meaning |
|---|---|
| **Pending** | Task created, not yet enqueued |
| **Queued** | In the queue, waiting for a worker |
| **Running** | A worker is executing the agent |
| **Succeeded** | Agent returned a result |
| **Failed** | Agent threw an error (may be retried) |
| **DeadLetter** | All retries exhausted, moved to dead-letter queue |

---

## Workflow Execution

A workflow is a DAG (directed acyclic graph) of nodes. When you call `POST /workflows/{id}/start`:

1. **Root nodes** (no incoming edges) are enqueued immediately
2. When a node **succeeds**, all downstream nodes are enqueued
3. When a node **fails**, it's retried up to `MaxRetries` times, then dead-lettered
4. **Human approval** nodes pause and wait for `POST .../approve` or `POST .../reject`
5. The workflow completes when all leaf nodes finish

---

## Queue Backends

| Backend | Use Case | Config |
|---|---|---|
| **In-Memory** | Local dev, tests | `USE_INMEMORY_QUEUE=true` |
| **Redis Streams** | Production | `REDIS_CONNECTION=localhost:6379` |
| **Kafka** | Enterprise (placeholder) | Coming soon |
| **SQS** | AWS (placeholder) | Coming soon |

The queue layer is abstracted behind an adapter interface, so adding new backends is straightforward.

---

## Agent Registry

The server ships with built-in agents:

| Agent Type | Provider | Config Required |
|---|---|---|
| `dummy` | Echo (for testing) | None |
| `openai` | OpenAI GPT models | `OPENAI_API_KEY` |
| `claude` | Anthropic Claude | `CLAUDE_API_KEY` |
| `copilot` | GitHub Copilot | `COPILOT_API_KEY` |

Custom agents implement the `IAgent` interface on the server side. From the SDK perspective, you just specify the agent type string — the server handles routing.

---

## Persistence

| Store | Dev Mode | Production |
|---|---|---|
| **Task Store** | In-memory | PostgreSQL |
| **Workflow Store** | In-memory | PostgreSQL |

When `DefaultConnection` is set, the server automatically runs migrations on startup and uses PostgreSQL. When it's empty, everything stays in-memory (lost on restart).

---

## Observability

| Endpoint | Format | Description |
|---|---|---|
| `GET /metrics` | Prometheus text | Counters, gauges, histograms |
| `GET /health` | Text | Health check |
| `GET /ready` | Text | Readiness probe (Kubernetes) |
| `GET /live` | Text | Liveness probe (Kubernetes) |

Structured logging via Serilog. Optional OpenTelemetry tracing with `OTEL_EXPORTER_OTLP_ENDPOINT`.

---

## Concurrency Control

Each agent type has a configurable concurrency limit (semaphore). This prevents overloading rate-limited APIs:

```bash
# Default for all agents
DEFAULT_AGENT_CONCURRENCY=2

# Override for a specific agent
CONCURRENCY_OPENAI=5
CONCURRENCY_CLAUDE=3
```

Prometheus gauges expose current vs. max concurrency per agent.
