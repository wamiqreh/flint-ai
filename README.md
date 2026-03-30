<div align="center">

# 🔥 Flint

**Production runtime for AI agents — queue, orchestrate, observe.**

[![PyPI](https://img.shields.io/pypi/v/flint-ai?style=flat-square&color=orange)](https://pypi.org/project/flint-ai/)
[![npm](https://img.shields.io/npm/v/@flintai/sdk?style=flat-square&color=red)](https://www.npmjs.com/package/@flintai/sdk)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](docker-compose.yml)

</div>

Flint wraps your existing AI agents (OpenAI, Claude, LangChain, anything) with production infrastructure: **queues, DAG workflows, human approval, retry/DLQ, and a live dashboard** — so you ship agents without building all that yourself.

> Think **"Temporal for AI agents, but simpler."**

![Workflow Editor](docs/assets/editor.png)

---

## Quickstart

```bash
docker compose -f docker-compose.dev.yml up -d

curl -X POST http://localhost:5156/tasks \
  -H "Content-Type: application/json" \
  -d '{"agentType": "dummy", "prompt": "Hello Flint!"}'

# Dashboard → http://localhost:5156/dashboard/index.html
# Editor   → http://localhost:5156/editor/index.html
```

For production (Postgres + Redis):

```bash
docker compose up -d
```

---

## Use with OpenAI (or any agent)

```bash
pip install flint-ai[openai]
```

```python
from flint_ai import OrchestratorClient, Workflow, Node, tool
from flint_ai.adapters.openai import FlintOpenAIAgent

@tool
def check_security(code: str) -> str:
    """Scan code for vulnerabilities."""
    return "No issues found"

reviewer = FlintOpenAIAgent(
    name="code_reviewer",
    model="gpt-4o",
    instructions="You are an expert code reviewer.",
    tools=[check_security],
)

wf = (Workflow("review-pipeline")
    .add(Node("review", agent=reviewer, prompt="Review this PR").requires_approval())
    .add(Node("summary", agent="dummy", prompt="Summarize").depends_on("review"))
)

# Registers agents, creates workflow, starts execution — one call
OrchestratorClient().deploy_workflow(wf)
```

Adapters exist for **OpenAI** and **CrewAI**. Any other framework works via webhooks:

```bash
curl -X POST http://localhost:5156/agents/register \
  -d '{"name": "my-agent", "url": "http://localhost:8000/execute"}'
```

Flint POSTs `{ prompt, metadata }` to your URL, you return `{ output }`. That's the whole contract.

---

## What you get

| | |
|---|---|
| **DAG workflows** | Fan-out, fan-in, conditional edges — build visually or via SDK |
| **Human-in-the-loop** | Pause any node for approval, approve from dashboard or API |
| **Retry + DLQ** | Auto-retry with backoff, dead-letter queue with bulk restart |
| **Live dashboard** | Task status, agent concurrency, DLQ inspect/retry — real-time |
| **Any agent** | OpenAI, Claude, CrewAI, LangChain, or plain HTTP webhooks |
| **One command deploy** | `docker compose up` — Postgres, Redis, API, Worker |

![Dashboard](docs/assets/dashboard.png)

---

## SDKs

```bash
pip install flint-ai          # Python — includes adapters, CLI, workflow builder
npm i @flintai/sdk             # TypeScript
dotnet add package Flint.AI    # C#
```

All SDKs expose the same core: `submitTask`, `createWorkflow`, `startWorkflow`, `approveTask`.

---

## Project structure

```
src/Orchestrator.Api/         # .NET API + Worker (the runtime)
sdks/python/flint_ai/         # Python SDK + native adapters
sdks/typescript/              # TypeScript SDK
sdks/dotnet/                  # C# SDK
examples/                     # Ready-to-run demos
```

**Key env vars:** `OPENAI_API_KEY`, `ConnectionStrings__DefaultConnection` (Postgres), `REDIS_CONNECTION` — see [docs/ENV_VARS.md](docs/ENV_VARS.md) for the full list.

---

## Roadmap

- [x] Core runtime — queue, DAG, retry, DLQ, human approval
- [x] Visual workflow editor + live dashboard
- [x] Native Python adapters — OpenAI, CrewAI
- [ ] LangGraph adapter
- [ ] Streaming support (SSE task output)
- [ ] Hosted tier (managed Flint — no Docker needed)
- [ ] Agent marketplace / template registry

---

<div align="center">

**[MIT License](LICENSE)** · **[Contributing](CONTRIBUTING.md)** · **[Docs](docs/QUICKSTART.md)**

</div>
