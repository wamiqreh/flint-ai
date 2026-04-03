<div align="center">

# 🔥 Flint

**Fault-tolerant orchestration for AI agents. Build → Queue → Retry → Observe.**

[![PyPI](https://img.shields.io/pypi/v/flint-ai?style=flat-square&color=orange)](https://pypi.org/project/flint-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-153%20passed-brightgreen?style=flat-square)]()


*Multi-agent pipelines with retry, dead-letter queues, and a dashboard — in 20 lines of Python.*

</div>

---

## Quick Start

```bash
pip install flint-ai[openai]
export OPENAI_API_KEY=sk-...          # Windows: set OPENAI_API_KEY=sk-...
```

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
    Workflow("research-pipeline")
    .add(Node("research", agent=researcher, prompt="AI orchestration 2025"))
    .add(Node("write", agent=writer, prompt="Summarize the research").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
    .run()  # Starts engine in-process — zero setup
)

print(results["research"])  # {"findings": [...]}
print(results["write"])     # "Executive summary: ..."
print(results["review"])    # {"score": 9, "feedback": "..."}
```

Nodes auto-receive upstream results. Failures retry with backoff. Dead agents go to DLQ. Dashboard shows it all.

---

## Why Flint

| You need | Flint gives you |
|----------|----------------|
| Agent fails mid-pipeline | Auto-retry with exponential backoff |
| Keeps failing forever | Dead Letter Queue — inspect, replay from dashboard |
| Human must approve a step | Built-in approval gates pause the DAG |
| Pass data between agents | Automatic — upstream output flows to downstream prompt |
| See what's happening | Real-time dashboard + DAG visualizer |
| Scale beyond one machine | Redis queues, Postgres store, AWS SQS |
| Keep API keys on your machine | Client-worker pattern — server orchestrates, agents run locally |

### vs. LangGraph / CrewAI / Temporal

- **LangGraph** — great for chains, but no built-in retry, DLQ, queue, or dashboard
- **CrewAI** — local-only, no server mode, no fault tolerance
- **Temporal** — battle-tested but heavy; Flint is `pip install` + 20 lines
- **Flint** — same code runs embedded (dev) or against a server (prod), agents always execute on **your** machine with **your** keys

---

## Two Run Modes, Same Code

### Embedded (dev — zero setup)

```python
results = workflow.run()                    # Engine starts in-process
# Dashboard at http://localhost:5160/ui/
```

### Server (prod — client-worker)

```bash
# Terminal 1: start server
python -m flint_ai.server --port 5156      # or: docker compose up -d
```

```python
# Terminal 2: your code — agents run HERE, server orchestrates
results = workflow.run(server_url="http://localhost:5156")
```

Server handles queues, DAG, retries, dashboard. Your `FlintWorker` claims tasks, executes locally, reports results back. **API keys never leave your machine.**

---

## Features

| Category | Details |
|----------|---------|
| **Workflows** | DAG execution, parallel branches, fan-out/fan-in, data passing |
| **Fault tolerance** | Retry with backoff, dead-letter queue, circuit breaker |
| **Human-in-the-loop** | Approval gates, reject/approve from dashboard or code |
| **Adapters** | OpenAI, LangChain, CrewAI — or `class MyAgent(FlintAdapter)` |
| **Infrastructure** | Redis Streams · AWS SQS · PostgreSQL · In-memory (dev) |
| **Observability** | Dashboard UI · Prometheus metrics · OpenTelemetry traces |
| **Security** | API key auth · CORS · Input validation · Request correlation IDs |
| **Deployment** | Docker · Kubernetes · Helm charts · Terraform (AWS) |

---

## Run the Examples

```bash
python scripts/run.py --list                                    # See all examples
python scripts/run.py examples/openai_workflow.py               # Embedded mode
python scripts/run.py examples/openai_workflow.py --mode server # Client-server mode
python scripts/run.py --server-only                             # Dashboard only
```

| Example | What it shows |
|---------|---------------|
| `openai_workflow.py` | 3-agent research pipeline |
| `openai_server_mode.py` | Same pipeline, client-worker mode |
| `parallel_branches.py` | Fan-out: 1 researcher → 3 parallel writers |
| `human_approval.py` | Approval gate pauses pipeline |
| `demo.py` | Minimal example (no API key needed) |

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

---

## License

[MIT](LICENSE)
