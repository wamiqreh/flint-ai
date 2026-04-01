<div align="center">

# 🔥 Flint

**Queue, orchestrate, and observe AI agents in production.**

[![PyPI](https://img.shields.io/pypi/v/flint-ai?style=flat-square&color=orange)](https://pypi.org/project/flint-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](docker-compose.yml)

</div>

---

## Install

```bash
pip install flint-ai[openai]
```

## 20 lines — three AI agents, one pipeline

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

print(results["research"])   # structured JSON
print(results["write"])      # article text
print(results["review"])     # scored review JSON
```

```
🔥 Flint — running workflow 'demo' (3 nodes)
  ✔ research  — 8s
  ✔ write     — 16s
  ✔ review    — 22s
✅ Done in 22s
```

Each node automatically receives output from its upstream dependencies — no glue code needed.

---

## Features

- **DAG workflows** — define complex pipelines with parallel branches, fan-out/fan-in
- **Data passing** — XCom-style: upstream results flow to downstream prompts automatically
- **Human approval gates** — pause workflows for human review before continuing
- **Retry + DLQ** — exponential backoff, dead-letter queue for failed tasks
- **Two run modes** — embedded (like Hangfire) or standalone Docker server
- **Adapters** — OpenAI, LangChain, CrewAI, or build your own
- **Dashboard UI** — monitor tasks, workflows, queues in real-time
- **Visual DAG editor** — drag-and-drop workflow design
- **Redis + Postgres** — production backends (in-memory for dev)
- **Prometheus metrics** — built-in observability

---

## Run modes

### Embedded (zero setup)

`.run()` auto-starts the engine inside your process — nothing to install or configure:

```python
results = Workflow("my-pipeline").add(...).run()
```

### Standalone server

Run Flint as a Docker service for shared/production use:

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
# Run any example (embedded mode — server starts automatically):
python scripts/run.py examples/demo.py

# Run with a standalone server:
python scripts/run.py examples/openai_workflow.py --mode server

# Start server only (then open dashboard):
python scripts/run.py --server-only

# List all examples:
python scripts/run.py --list
```

| Example | Description |
|---------|-------------|
| `demo.py` | Minimal 3-agent pipeline (research → write → review) |
| `openai_workflow.py` | OpenAI agents with data passing between nodes |
| `parallel_branches.py` | Fan-out DAG: one research node feeds 3 parallel writers |
| `human_approval.py` | Workflow with a human approval gate |
| `embedded_demo.py` | Embedded server mode (like Hangfire/Celery) |
| `crewai_example.py` | CrewAI integration via orchestrator tools |
| `langchain_adapter_example.py` | LangChain runnable adapter |
| `workflow_builder_example.py` | Fluent DSL for building workflows programmatically |

---

## Project structure

```
flint-ai/
├── flint_ai/                  # Python package
│   ├── workflow_builder.py    # Workflow & Node fluent API
│   ├── adapters/              # OpenAI, CrewAI, LangChain adapters
│   └── server/                # Full server implementation
│       ├── engine/            # Task engine, models, state
│       ├── dag/               # DAG engine, XCom context
│       ├── worker/            # Background task workers
│       ├── queue/             # Redis queue backend
│       ├── store/             # Postgres task store
│       ├── api/               # FastAPI routes
│       └── ui/                # React dashboard + DAG editor
├── examples/                  # Ready-to-run examples
├── scripts/                   # Runner scripts
├── tests/                     # Test suite
├── docker-compose.yml         # Redis + Postgres + Flint server
├── Dockerfile                 # Production container
└── pyproject.toml             # Package config
```

---

## License

[MIT](LICENSE)
