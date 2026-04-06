# AGENTS.md — Flint AI

> Read this file first. Load skills on-demand.

## Project

Fault-tolerant AI agent orchestration. `pip install flint-ai`. Python 3.10+.

## Routing — Load Skills When Relevant

| When you see... | Load skill |
|-----------------|-----------|
| "create adapter", "new agent", "integrate [LLM provider]" | `skills/adapter-dev.md` |
| "new queue", "RabbitMQ", "Kafka", "queue backend" | `skills/queue-backend.md` |
| "new store", "MongoDB", "DynamoDB", "store backend" | `skills/store-backend.md` |
| "DAG", "workflow engine", "fan-out", "cycle", "topological" | `skills/dag-engine.md` |
| "write test", "test coverage", "mock", "pytest" | `skills/testing.md` |
| "docker", "k8s", "helm", "terraform", "deploy" | `skills/deployment.md` |
| "endpoint", "route", "API", "dashboard", "HTTP" | `skills/api-dev.md` |
| "cost tracking", "token usage", "tool logging", "FlintCostTracker" | `skills/cost-tracking.md` |

## Dev Commands

```bash
pip install -e ".[all]"        # Install
pytest tests/ -v               # Tests
./scripts/dev.sh all           # Lint + typecheck + test
```

## Two Agent Systems (DO NOT CONFUSE)

| System | Location | Use |
|--------|----------|-----|
| **FlintAdapter** | `flint_ai/adapters/` | Client-side, YOUR API keys |
| **BaseAgent** | `flint_ai/server/agents/` | Server-side, internal workers |

## Key Rule

Server orchestrates. Agents execute on client. API keys never leave your machine.

## File Map

| Path | What |
|------|------|
| `flint_ai/workflow_builder.py` | User-facing Workflow/Node DSL |
| `flint_ai/server/engine/task_engine.py` | Task lifecycle (submit→claim→retry→DLQ) |
| `flint_ai/server/dag/engine.py` | DAG execution (validation, fan-out/fan-in, recovery) |
| `flint_ai/server/queue/` | Queue backends (memory, redis, sqs) |
| `flint_ai/server/store/` | Store backends (memory, postgres) |
| `flint_ai/server/app.py` | FastAPI app factory |
| `flint_ai/adapters/core/cost_tracker.py` | Cost tracking (FlintCostTracker, TimeBoundPrice) |
| `flint_ai/adapters/core/sanitization.py` | Input sanitization for tool logging |
| `flint_ai/adapters/openai/agent.py` | OpenAI adapter with cost + tool tracking |
| `flint_ai/server/api/dashboard.py` | Dashboard API (cost, tools endpoints) |
| `flint_ai/server/ui/src/pages/` | Frontend pages (CostsPage, ToolTracePage, RunsPage) |
| `examples/basics/` | Core examples (no API key needed) |
| `examples/openai/` | OpenAI adapter examples |
| `examples/advanced/` | Production scenarios, cost tracking, full demos |

## Critical Patterns

- **CAS is atomic:** New stores MUST use atomic compare-and-swap, not read-check-update
- **DLQ = Redis Stream:** Uses `XRANGE`/`XADD`/`XDEL`, not a separate queue
- **Heartbeat = 15s:** Workers must heartbeat or `XAUTOCLAIM` steals the task
- **Fan-in = ALL deps:** Node with multiple deps waits for ALL to succeed

## Before Committing — DO NOT SKIP

1. `python -m ruff check flint_ai/ tests/ scripts/` — zero lint errors
2. `python -m ruff format --check flint_ai/ tests/ scripts/` — zero format issues
3. `python -m pytest tests/ -q` — all tests pass
4. **Check `pyproject.toml`** — version constraints match reality (Python min, dependency versions)
5. **Check CI workflows** — no hardcoded versions that conflict with `pyproject.toml`

## Pre-commit Hook

Install once: `cp .githooks/pre-commit .git/hooks/pre-commit`
Then every commit auto-runs lint + format + tests.
