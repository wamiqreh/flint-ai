<div align="center">

# 🔥 Flint

**Production-grade AI agent orchestration. Queue, retry, observe.**

[![PyPI](https://img.shields.io/pypi/v/flint-ai?style=flat-square&color=orange)](https://pypi.org/project/flint-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](docker-compose.yml)
[![Tests](https://img.shields.io/badge/tests-143%20passed-brightgreen?style=flat-square)]()

*Your AI agents crash. Flint catches them, retries them, and shows you what happened.*

</div>

---

## Install

```bash
pip install flint-ai[openai]
```

## 15 lines — three agents, fault-tolerant pipeline

```python
from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(name="researcher", model="gpt-4o-mini",
    instructions="Research the topic. Return key findings.",
    response_format={"type": "json_object"})
writer = FlintOpenAIAgent(name="writer", model="gpt-4o-mini",
    instructions="Write a polished summary from the research.")
reviewer = FlintOpenAIAgent(name="reviewer", model="gpt-4o-mini",
    instructions="Review the article. Score out of 10.",
    response_format={"type": "json_object"})

results = (
    Workflow("demo")
    .add(Node("research", agent=researcher, prompt="AI orchestration 2025"))
    .add(Node("write", agent=writer, prompt="Summarize the research").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
    .run()
)
```

Each node automatically receives upstream results. If a node fails, it retries with exponential backoff. If it keeps failing, it goes to the dead letter queue. You see it all in the dashboard.

---

## What Flint does

| Problem | Flint's answer |
|---------|---------------|
| Agent fails mid-pipeline | Auto-retry with exponential backoff |
| Keeps failing | Routes to Dead Letter Queue, notifies you |
| Need human review | Built-in approval gates pause the pipeline |
| Results don't flow between agents | XCom-style data passing — automatic |
| No visibility | Real-time dashboard + DAG visualizer |
| Scaling | Redis queues, Postgres store, SQS adapter |

## Architecture

```
Your Code → Flint SDK → Queue (Redis/SQS/Memory) → Worker Pool → Agent Adapters
                ↓                                        ↓
           Dashboard UI ←── FastAPI Server ←── Task Engine (retry/DLQ/circuit breaker)
```

---

## Features

- **DAG workflows** — parallel branches, fan-out/fan-in, conditional edges
- **Data passing** — upstream results flow to downstream prompts automatically
- **Human approval gates** — pause workflows for human review
- **Retry + DLQ** — exponential backoff, dead-letter queue, configurable per-agent
- **Circuit breaker** — protects backends from cascade failures
- **Two run modes** — embedded (like Hangfire) or standalone Docker server
- **Adapters** — OpenAI, LangChain, CrewAI, or build your own
- **Dashboard UI** — monitor tasks, workflows, DLQ in real-time
- **Visual DAG editor** — drag-and-drop workflow design
- **Queue backends** — Redis Streams, AWS SQS, in-memory
- **Store backends** — PostgreSQL, in-memory
- **Security** — API key auth, CORS, input validation, request correlation IDs
- **Prometheus metrics** — built-in observability

---

## Run modes

### Embedded (zero setup)

`.run()` starts the engine inside your process — nothing to install:

```python
results = Workflow("my-pipeline").add(...).run()
```

### Standalone server

```bash
docker compose up -d                          # Redis + Postgres + Flint
open http://localhost:5156/ui/                 # Dashboard
```

Or without Docker:

```bash
python -m flint_ai.server --port 5156
```

---

## Examples

```bash
# Run any example (embedded — server starts automatically):
python scripts/run.py examples/demo.py

# Run with standalone server:
python scripts/run.py examples/openai_workflow.py --mode server

# Start server only (then open dashboard):
python scripts/run.py --server-only

# List all examples:
python scripts/run.py --list
```

| Example | What it shows |
|---------|---------------|
| `demo.py` | Minimal 3-agent pipeline |
| `openai_workflow.py` | OpenAI agents with data passing |
| `parallel_branches.py` | Fan-out: 1 research → 3 parallel writers |
| `human_approval.py` | Human approval gate |
| `embedded_demo.py` | In-process server (Hangfire-style) |
| `crewai_example.py` | CrewAI integration |
| `langchain_adapter_example.py` | LangChain adapter |
| `workflow_builder_example.py` | Fluent DSL |

---

## Project structure

```
flint-ai/
├── flint_ai/                  # Python package
│   ├── workflow_builder.py    # Workflow & Node fluent API
│   ├── adapters/              # OpenAI, CrewAI, LangChain adapters
│   └── server/                # Full server
│       ├── engine/            # Task lifecycle, state machine
│       ├── dag/               # DAG engine, XCom context
│       ├── worker/            # Background workers
│       ├── queue/             # Redis, SQS, in-memory
│       ├── store/             # Postgres, in-memory
│       ├── middleware/        # Auth, CORS, validation, circuit breaker
│       ├── api/               # FastAPI routes
│       └── ui/                # React dashboard + DAG editor
├── examples/                  # Ready-to-run examples
├── scripts/                   # Runner scripts
├── tests/                     # 143 tests
├── docker-compose.yml         # Redis + Postgres + Flint
├── Dockerfile                 # Production container
└── pyproject.toml             # Package config
```

---

## License

[MIT](LICENSE)
