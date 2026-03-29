# 🔗 Code Review Pipeline

A sequential 3-stage workflow that generates code, reviews it, and produces a
final summary report — demonstrating Flint's linear prompt-chaining pattern.

```
┌──────────┐     ┌──────────┐     ┌───────────┐
│ generate  │────▶│  review   │────▶│ summarize │
│ (openai)  │     │ (claude)  │     │  (dummy)  │
└──────────┘     └──────────┘     └───────────┘
```

## What It Does

1. **generate** — Writes a Python function based on a prompt.
2. **review** — Performs a code review: bugs, style, improvements.
3. **summarize** — Produces a concise final report combining code + review.

Each node's output feeds into the next node's context, showing how Flint
chains agent results through a DAG.

## Prerequisites

- Flint running locally: `docker compose -f docker-compose.dev.yml up -d`
- Python 3.10+: `pip install flint-ai`

## Run

```bash
python workflow.py
```

## What Happens

1. The script builds a 3-node workflow using the Flint Python DSL.
2. It submits the workflow to the Flint API (`POST /workflows`).
3. It starts execution (`POST /workflows/{id}/start`).
4. It polls each node until the pipeline completes.
5. Final results are printed to the console.

## Try in the Visual Editor

1. Open **http://localhost:5156/editor/**
2. Click **Import JSON**
3. Load `workflow.json`
4. Click **Deploy**
