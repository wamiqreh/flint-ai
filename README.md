<div align="center">

# 🔥 Flint

**Fault-tolerant AI agent orchestration.**

Build → Queue → Retry → Observe.

</div>

---

## 20 Lines. Full Pipeline.

```python
from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

agent = FlintOpenAIAgent(name="writer", model="gpt-4o-mini")

results = (
    Workflow("pipeline")
    .add(Node("research", agent=agent, prompt="AI trends 2025"))
    .add(Node("write", agent=agent, prompt="{research}").depends_on("research"))
    .run()
)
```

Agent calls OpenAI → task queued → retries on failure → dead-letter if broken → costs tracked → dashboard at `localhost:5160/ui/`.

All of that, zero setup.

---

## Why Flint

| If you need | Flint gives you |
|-------------|----------------|
| Agent fails | Auto-retry with backoff |
| Keeps failing | Dead Letter Queue — inspect & retry from dashboard |
| Human must approve | Approval gates pause the DAG |
| Crash mid-execution | DB heartbeat → auto-recovery on restart |
| See what's happening | Live dashboard: costs, traces, DAG view |
| API keys stay yours | Server orchestrates, agents run on **your** PC |

---

## Two Modes, Same Code

### Global Engine — Start Once, Run Many

```python
from flint_ai import configure_engine, shutdown_engine, Workflow, Node

configure_engine(agents=[agent])  # background worker pool

Workflow("task-1").add(Node("s", agent, prompt="...")).run()
Workflow("task-2").add(Node("s", agent, prompt="...")).run()

shutdown_engine()
```

### Server + Worker — Distributed

```bash
# Terminal 1
docker compose up -d
```

```python
# Terminal 2 — agents run HERE
worker = FlintWorker(server_url="http://localhost:5156")
worker.register("writer", agent)

Workflow("task").add(Node("s", agent, prompt="...")).run(server_url="http://localhost:5156")
```

---

## Install

```bash
pip install flint-ai
```

---

## Cost Tracking — Built In

No boilerplate. Cost is auto-tracked per model, per task, per workflow.

```python
agent = FlintOpenAIAgent(name="writer", model="gpt-4o-mini")
# that's it — cost tracked automatically
```

View costs at `localhost:5160/ui/costs`:
- Cost by model · timeline · per-task breakdown
- Per-tool-call costs · cumulative workflow cost
- Click any task → full token & cost breakdown

Pricing comes from database. Override per agent if needed:

```python
agent = FlintOpenAIAgent(name="writer", model="gpt-4o-mini",
    cost_config_override={"prompt": 3.0, "completion": 12.0})
```

---

## Quickstart

| Example | What |
|---------|------|
| `01_embedded_enqueue.py` | Start once, enqueue many |
| `02_embedded_run_once.py` | Run single workflow |
| `03_sequential_pipeline.py` | A → B → C |
| `04_fanout_fanin.py` | A → (B, C) → D |
| `05_approval_gate.py` | Pause for human approval |
| `06_server_enqueue.py` | Connect to server, enqueue |
| `07_server_run_once.py` | Connect, run, disconnect |

```bash
python examples/quickstart/01_embedded_enqueue.py
```

---

## Dashboard

When running (embedded or server):

| Page | What |
|------|------|
| `/ui/` | Overview — queue lengths, recent runs |
| `/ui/costs` | Cost by model, timeline, per-task breakdown |
| `/ui/tools` | Tool execution tree, errors with traces |
| `/ui/runs` | Workflow runs with DAG visualization |
| `/docs` | Swagger API |

---

## Crash Recovery

| What crashes | What happens |
|-------------|-------------|
| Worker mid-task | DB heartbeat stops → stale task detected → auto-requeued |
| Server | Agents auto-reconstruct from DB, failed tasks re-queued |
| Both | All non-terminal tasks restored on startup |

Tasks survive any crash. No data loss with PostgreSQL + Redis.

---

## Build Your Own Agent

```python
from flint_ai import FlintAdapter, AgentRunResult

class MyAgent(FlintAdapter):
    name = "my-agent"

    async def run(self, input_data: dict) -> AgentRunResult:
        result = await call_my_llm(input_data["prompt"])
        return AgentRunResult(output=result)
```

Register it and it just works — retry, DLQ, cost tracking, dashboard.

---

## License

[MIT](LICENSE)
