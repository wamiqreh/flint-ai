<div align="center">

# 🔥 Flint

**Queue, orchestrate, and observe AI agents in production.**

[![PyPI](https://img.shields.io/pypi/v/flint-ai?style=flat-square&color=orange)](https://pypi.org/project/flint-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](docker-compose.yml)

</div>

---

## Run it

```bash
docker compose -f docker-compose.dev.yml up -d
pip install flint-ai
```

Dashboard → `http://localhost:5156/dashboard/index.html`
Editor → `http://localhost:5156/editor/index.html`

---

## Build a pipeline in Python

Three agents chained as a DAG — each waits for the previous to finish:

```python
from flint_ai import Workflow, Node, AsyncOrchestratorClient
from flint_ai.adapters.core.base import FlintAdapter
from flint_ai.adapters.core.types import AgentRunResult
from flint_ai.adapters.core.worker import start_worker
import asyncio

class Researcher(FlintAdapter):
    def __init__(self):
        super().__init__(name="researcher")

    async def run(self, input_data: dict) -> AgentRunResult:
        return AgentRunResult(output=f"Research on: {input_data['prompt']}")

class Writer(FlintAdapter):
    def __init__(self):
        super().__init__(name="writer")

    async def run(self, input_data: dict) -> AgentRunResult:
        return AgentRunResult(output=f"Article based on: {input_data['prompt']}")

class Reviewer(FlintAdapter):
    def __init__(self):
        super().__init__(name="reviewer")

    async def run(self, input_data: dict) -> AgentRunResult:
        return AgentRunResult(output="Score: 8.5/10 — APPROVED")

async def main():
    await start_worker(port=5157)

    workflow = (
        Workflow("research-pipeline")
        .add(Node("research", agent=Researcher(), prompt="AI orchestration market"))
        .add(Node("write",    agent=Writer(),     prompt="Write summary").depends_on("research"))
        .add(Node("review",   agent=Reviewer(),   prompt="Review article").depends_on("write"))
    )

    async with AsyncOrchestratorClient() as client:
        workflow_id = await client.deploy_workflow(workflow)
        print(f"Running: {workflow_id}")

asyncio.run(main())
```

```
✔ research (researcher) succeeded [3.1s]
✔ write    (writer)     succeeded [6.1s]
✔ review   (reviewer)   succeeded [9.2s]
✅ Pipeline completed in 9.2s
```

See [`examples/three-agent-pipeline/main.py`](examples/three-agent-pipeline/main.py) for the full runnable version.

---

## Use with OpenAI

```bash
pip install flint-ai[openai]
```

```python
from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

agent = FlintOpenAIAgent(name="analyst", model="gpt-4o", instructions="You are a data analyst.")

wf = (Workflow("analysis")
    .add(Node("analyze", agent=agent, prompt="Analyze Q4 trends").requires_approval())
    .add(Node("report", agent=agent, prompt="Write report").depends_on("analyze"))
)
```

Adapters: **OpenAI** · **CrewAI** · **LangGraph** — or any HTTP endpoint via [webhooks](docs/QUICKSTART.md).

---

## Visual editor

Design workflows visually — drag nodes, set dependencies, configure agents and human approval.

![Workflow Editor](docs/assets/editor.png)

---

## Live dashboard

Monitor tasks, agents, retry queues, and DLQ in real-time. Approve pending tasks, restart failures, stream live output.

![Dashboard](docs/assets/dashboard.png)

---

## License

[MIT](LICENSE)
