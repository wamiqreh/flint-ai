# 🔥 Flint — Spark Your Agent Workflows

The queue-driven runtime for AI agent orchestration.
Submit tasks, build DAG workflows, watch agents execute — all from a single API.

[![PyPI](https://img.shields.io/pypi/v/flint-ai)](https://pypi.org/project/flint-ai/)
[![npm](https://img.shields.io/npm/v/@flintai/sdk)](https://www.npmjs.com/package/@flintai/sdk)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Quickstart](#-quickstart) · [Demos](#-demos) · [SDKs](#-sdks) · [Dashboard](#️-dashboard--editor) · [Docs](docs/QUICKSTART.md)

---

## What is Flint?

Flint is a queue-based orchestration runtime that executes AI agent tasks with retries, dead-letter queues, and DAG workflows out of the box. It works with any AI agent — OpenAI, Claude, Copilot, or your own — and ships with a visual workflow editor and live dashboard. Run it anywhere with a single `docker compose up`.

---

## ⚡ Quickstart

```bash
# 1. Start Flint
docker compose -f docker-compose.dev.yml up -d

# 2. Submit a task
curl -X POST http://localhost:5156/tasks \
  -H "Content-Type: application/json" \
  -d '{"agent": "dummy", "prompt": "Hello Flint!"}'

# 3. Install Python SDK
pip install flint-ai

# 4. Run a workflow
python -c "
from flint_ai import OrchestratorClient, Workflow, Node

client = OrchestratorClient('http://localhost:5156')
wf = (Workflow('hello')
    .add(Node('think', agent='dummy', prompt='Think of something'))
    .add(Node('write', agent='dummy', prompt='Write it up').depends_on('think'))
    .build())
client.create_workflow(wf)
client.start_workflow('hello')
print('🔥 Check http://localhost:5156/dashboard/')
"
```

---

## 🎯 Demos

| Demo | Pattern | Description |
|------|---------|-------------|
| [Code Review Pipeline](examples/demos/code-review-pipeline/) | Sequential chain | generate → review → summarize |
| [Document Summarizer](examples/demos/document-summarizer/) | Fan-out/fan-in | split → parallel chunks → merge |
| [Research Agent Team](examples/demos/research-agent-team/) | Complex DAG | planner → parallel researchers → analyst → writer |

---

## ✨ Features

| | |
|---|---|
| 🔄 **Queue-driven execution** — Redis Streams, in-memory, pluggable backends | 🌊 **DAG workflows** — fan-out, fan-in, conditional routing, approval gates |
| 🤖 **Any AI agent** — OpenAI, Claude, Copilot, or bring your own | 📊 **Live dashboard** — real-time metrics, agent concurrency, DLQ inspector |
| 🎨 **Visual editor** — drag-and-drop workflow builder, deploy in one click | 🐍 **Multi-language SDKs** — Python, TypeScript, C# — all with workflow DSL |
| 🔌 **Framework adapters** — LangChain, CrewAI, AutoGen, FastAPI, Express, Next.js | 📈 **Observability** — Prometheus metrics, OpenTelemetry tracing, Grafana dashboards |
| 🐳 **One-command deploy** — Docker Compose for dev, prod, and monitoring | ♻️ **Resilient** — Exponential backoff, retry-after, dead-letter queues, webhooks |

---

## 📦 SDKs

### Python

```bash
pip install flint-ai
```

```python
from flint_ai import OrchestratorClient
client = OrchestratorClient("http://localhost:5156")
task_id = client.submit_task("openai", "Summarize this PR")
print(client.wait_for_task(task_id))
```

### TypeScript

```bash
npm install @flintai/sdk
```

```typescript
import { OrchestratorClient } from "@flintai/sdk";
const client = new OrchestratorClient("http://localhost:5156");
const taskId = await client.submitTask("openai", "Summarize this PR");
console.log(await client.waitForTask(taskId));
```

### C#

```bash
dotnet add package Flint.AI
```

```csharp
using FlintAI.Sdk;
var client = new OrchestratorClient("http://localhost:5156");
var taskId = await client.SubmitTaskAsync("openai", "Summarize this PR");
Console.WriteLine(await client.WaitForTaskAsync(taskId));
```

---

## 🖥️ Dashboard & Editor

- **Dashboard** → `http://localhost:5156/dashboard/` — real-time task metrics, agent status, DLQ inspector
  <!-- ![Dashboard screenshot](docs/assets/dashboard.png) -->
- **Editor** → `http://localhost:5156/editor/` — drag-and-drop DAG builder, one-click deploy
  <!-- ![Editor screenshot](docs/assets/editor.png) -->

---

## 🏗️ Architecture

```
Client → API (port 5156) → Queue (Redis/in-memory) → Worker → Agent → Result
                         ↘ Workflow Engine (DAG) ↗
```

---

## 🚀 Scaffold a New Project

```bash
pip install flint-ai[cli]
flint init my-project
cd my-project && docker compose up -d
python workflow.py
```

---

## 📚 Learn More

| Resource | Link |
|----------|------|
| 10-Minute Quickstart | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| API Reference | [Swagger UI](http://localhost:5156/swagger/) |
| Environment Variables | [docs/ENV_VARS.md](docs/ENV_VARS.md) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## License

[MIT](LICENSE)
