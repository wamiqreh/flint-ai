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

**Or use Claude (Anthropic):**

```bash
pip install flint-ai
export ANTHROPIC_API_KEY=sk-ant-...   # Windows: set ANTHROPIC_API_KEY=sk-ant-...
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

### Embedded Mode & Dashboard

When you call `.run()`, Flint starts a full server **in-process** (like Hangfire). No separate server process needed:

```python
results = Workflow(...).add(...).run()
# ✅ Dashboard live at http://localhost:5160/ui/
# ✅ All state in-memory (or Redis/Postgres if configured)
# ✅ Workflow auto-stops when `.run()` completes
```

**Persistence (like Hangfire):**
```python
# In-memory (default) — state lost on process exit
engine = FlintEngine(ServerConfig(port=5160))

# Persistent (Redis) — survives process restart
engine = FlintEngine(ServerConfig(
    port=5160,
    queue_backend="redis",
    redis_url="redis://localhost:6379"
))

# Production (Postgres + Redis) — fully resilient
engine = FlintEngine(ServerConfig(
    port=5160,
    queue_backend="redis",
    store_backend="postgres",
    redis_url="redis://localhost:6379",
    postgres_url="postgresql://user:pass@localhost:5432/flint"
))
```

For details on setup, see [Deployment & Advanced Config](#deployment--advanced-config) below.

### Using Claude (Anthropic)

Same code pattern, just swap the adapter:

```python
from flint_ai.adapters.anthropic import FlintAnthropicAgent

researcher = FlintAnthropicAgent(
    name="researcher",
    model="claude-3-5-sonnet-20241022",  # or claude-3-opus-20250219, claude-3-haiku-20240307
    instructions="Research the topic. Return findings.",
)

# Rest of pipeline identical to OpenAI
results = (
    Workflow("research-pipeline")
    .add(Node("research", agent=researcher, prompt="AI orchestration 2025"))
    .run()
)
```

Supports:
- **Claude 3.5 Sonnet** — best balance of speed/cost
- **Claude 3 Opus** — most capable, higher cost
- **Claude 3 Haiku** — fastest, cheapest
- **Tool calling** — automatic with same `@tool` decorator
- **Vision** — image analysis (via calculate_vision)



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
| **Adapters** | OpenAI, Anthropic (Claude), LangChain, CrewAI — or `class MyAgent(FlintAdapter)` |
| **Infrastructure** | Redis Streams · AWS SQS · PostgreSQL · In-memory (dev) |
| **Observability** | Dashboard UI · Prometheus metrics · OpenTelemetry traces |
| **Security** | API key auth · CORS · Input validation · Request correlation IDs |
| **Deployment** | Docker · Kubernetes · Helm charts · Terraform (AWS) |

---

## Cost Tracking & Tool Logging <sub>⚠️ Experimental</sub>

> **Status:** Experimental — API may change. Works with OpenAI and Anthropic adapters.

Track token usage, USD cost, and every tool call execution across your workflows. Supports text, vision, embeddings, and image generation models.

```python
from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.adapters.anthropic import FlintAnthropicAgent
from flint_ai.adapters.core.cost_tracker import FlintCostTracker, TimeBoundPrice
from flint_ai import tool
from datetime import datetime, timezone

# Define tools
@tool
def search_code(query: str) -> str:
    return f"Found results for '{query}'"

# Unified cost tracking for OpenAI and Claude
tracker = FlintCostTracker()

# Custom pricing (time-bound)
tracker.add_time_bound_price(TimeBoundPrice(
    model="gpt-4o-mini",
    prompt_cost_per_million=0.150,
    completion_cost_per_million=0.600,
    vision_input_cost_per_million=0.075,  # For vision-enabled models
    effective_from=datetime(2024, 7, 18, tzinfo=timezone.utc),
))

# OpenAI agent with cost tracking
openai_agent = FlintOpenAIAgent(
    name="openai_researcher",
    model="gpt-4o-mini",
    instructions="Research and summarize.",
    tools=[search_code],
    cost_tracker=tracker,
)

# Claude agent with same cost tracking
claude_agent = FlintAnthropicAgent(
    name="claude_researcher",
    model="claude-3-5-sonnet-20241022",
    instructions="Research and summarize.",
    tools=[search_code],
    cost_tracker=tracker,  # Shared tracker
)

results = (
    Workflow("multi-model-cost-tracked")
    .add(Node("openai_research", agent=openai_agent, prompt="Research Python async"))
    .add(Node("claude_research", agent=claude_agent, prompt="Research Rust async"))
    .run()
)

# Cost is captured in task metadata and visible in the dashboard
# Dashboard: http://localhost:5160/ui/costs
# Tool trace: http://localhost:5160/ui/tools
```

### Supported Model Types

| Model Type | Example | Cost Calculation |
|-----------|---------|------------------|
| **Text** | GPT-4o, Claude 3 Sonnet | `prompt_tokens * prompt_cost + completion_tokens * completion_cost` |
| **Vision** | GPT-4o with images, Claude 3 with vision | `image_tokens * vision_cost + prompt_tokens * prompt_cost + ...` |
| **Embeddings** | text-embedding-3-small/large | `input_tokens * embedding_cost` |
| **Image Gen** | DALL·E 3 | Per-image cost (configurable) |

### What's tracked

| Metric | Where |
|--------|-------|
| Prompt/completion tokens | `AgentRunResult.cost` |
| USD cost per model | Task metadata `cost_breakdown` |
| Per-tool-call duration | `ToolExecution.duration_ms` |
| Per-tool-call errors | `ToolExecution.error` + `stack_trace` |
| Cumulative workflow cost | `/dashboard/cost/workflow/{run_id}` |

### Dashboard pages

- **`/ui/costs`** — Cost by model, cost over time, per-task cost table
- **`/ui/tools`** — Tool execution tree, error details with stack traces
- **`/ui/runs`** — Workflow runs with DAG visualization, per-node cost/duration

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
| `claude_workflow.py` | Same pipeline with Claude (Anthropic) |
| `claude_vision_example.py` | Vision analysis with cost tracking |
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
