# ⚡ Quickstart

Go from zero to running AI agent workflows.

**Prerequisites:** Python 3.9+

---

## Step 1 — Install

```bash
pip install flint-ai[openai]
```

## Step 2 — Run the demo

```bash
export OPENAI_API_KEY=sk-...
python examples/demo.py
```

```
🔥 Flint — running workflow 'demo' (3 nodes)
  ✔ research  — 8s
  ✔ write     — 16s
  ✔ review    — 22s
✅ Done in 22s
```

That's it. Three AI agents — research, write, review — chained in a pipeline.
No server setup, no config. `.run()` starts everything automatically.

---

## Step 3 — Run with a standalone server

For shared use, dashboards, or production:

```bash
# Option A: Docker (recommended)
docker compose up -d
open http://localhost:5156/ui/

# Option B: Python
python -m flint_ai.server --port 5156
```

Then run examples against the server:

```bash
python scripts/run.py examples/openai_workflow.py --mode server
```

---

## Step 4 — Explore

| What | Where |
|------|-------|
| Dashboard UI | http://localhost:5156/ui/ |
| API docs (Swagger) | http://localhost:5156/docs |
| All examples | `python scripts/run.py --list` |
| Configuration | [Environment Variables](ENV_VARS.md) |

---

## What's next?

- Browse [examples/](../examples/) for OpenAI workflows, parallel branches, human approval, CrewAI, LangChain
- Read the [Python SDK docs](../docs-site/python-sdk.md) for the full API reference
- Check the [Architecture guide](../docs-site/architecture.md) for how the DAG engine, workers, and queues fit together
