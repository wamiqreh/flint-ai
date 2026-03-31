<div align="center">

# 🔥 Flint

**Queue, orchestrate, and observe AI agents in production.**

[![PyPI](https://img.shields.io/pypi/v/flint-ai?style=flat-square&color=orange)](https://pypi.org/project/flint-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](docker-compose.yml)

</div>

---

## Quick start

```bash
docker compose -f docker-compose.dev.yml up -d   # starts Flint runtime
pip install flint-ai[openai]
```

## Three GPT-4o-mini agents, one pipeline

Each agent automatically receives the previous agent's output — no glue code:

```python
import asyncio
from flint_ai import Workflow, Node, AsyncOrchestratorClient
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.adapters.core.worker import start_worker

researcher = FlintOpenAIAgent(
    name="researcher", model="gpt-4o-mini",
    instructions="Research the topic. Return 3-5 key findings.",
    response_format={"type": "json_object"},
)
writer = FlintOpenAIAgent(
    name="writer", model="gpt-4o-mini",
    instructions="Write a polished executive summary from the research.",
)
reviewer = FlintOpenAIAgent(
    name="reviewer", model="gpt-4o-mini",
    instructions="Review the article. Score out of 10.",
    response_format={"type": "json_object"},
)

workflow = (
    Workflow("research-pipeline")
    .add(Node("research", agent=researcher, prompt="AI agent orchestration in 2025"))
    .add(Node("write",    agent=writer,     prompt="Summarize the research").depends_on("research"))
    .add(Node("review",   agent=reviewer,   prompt="Review this article").depends_on("write"))
)

async def main():
    await start_worker(port=5157)
    async with AsyncOrchestratorClient() as client:
        wf_id = await client.deploy_workflow(workflow)
        print(f"Running: {wf_id}")
        print(f"Dashboard: http://localhost:5156/dashboard/index.html")

asyncio.run(main())
```

```
✔ research  (researcher) — 10s
✔ write     (writer)     — 16s
✔ review    (reviewer)   — 22s
✅ Pipeline completed in 24s
```

See [`examples/demo.py`](examples/demo.py) for the full runnable version with Pydantic structured output.

---

## Visual editor

Design workflows visually — drag nodes, set dependencies, configure agents and human approval.

![Workflow Editor](docs/assets/editor.png)

---

## Live dashboard

Monitor tasks, agents, retry queues, and DLQ in real-time.

![Dashboard](docs/assets/dashboard.png)

---

## License

[MIT](LICENSE)
