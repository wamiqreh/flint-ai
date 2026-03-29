# 🔬 Research Agent Team

A complex multi-agent workflow with parallel branches, a human-in-the-loop
approval gate, and multi-stage synthesis — demonstrating Flint's full DAG
orchestration capabilities.

```
                    ┌──────────────┐
               ┌───▶│ researcher-1 │───┐
               │    └──────────────┘   │
┌─────────┐    │    ┌──────────────┐   │    ┌──────────┐    ┌────────┐
│ planner  │───┼───▶│ researcher-2 │───┼───▶│ analyst  │───▶│ writer │
└─────────┘    │    │  🔒 approval │   │    └──────────┘    └────────┘
               │    └──────────────┘   │
               │                       │
               └───────────────────────┘
```

## What It Does

1. **planner** — Creates a structured research plan with specific questions.
2. **researcher-1** — Gathers data on market trends (runs in parallel).
3. **researcher-2** — Gathers data on technical capabilities (runs in
   parallel). Has **`requires_approval=True`** — Flint will pause execution
   and wait for human approval before this node runs.
4. **analyst** — Synthesizes findings from both researchers into insights.
5. **writer** — Produces the final polished research report.

## Key Features Demonstrated

- **Parallel execution**: researcher-1 and researcher-2 run concurrently
- **Human-in-the-loop**: researcher-2 requires manual approval before starting
- **Complex DAG**: diamond-shaped dependency graph with fan-out and fan-in
- **Multi-agent collaboration**: 5 specialized agents working together

## Prerequisites

- Flint running locally: `docker compose -f docker-compose.dev.yml up -d`
- Python 3.10+: `pip install flint-ai`

## Run

```bash
python research.py
```

## What Happens

1. The script builds a 5-node DAG with parallel branches and an approval gate.
2. After submission, **planner** runs first.
3. When planner completes, **researcher-1** starts immediately.
4. **researcher-2** enters a `PendingApproval` state — the script prompts you
   to approve it (or it auto-approves in non-interactive mode).
5. Once both researchers finish, **analyst** synthesizes their findings.
6. Finally, **writer** produces the report.
7. A complete execution timeline is printed.

## Try in the Visual Editor

1. Open **http://localhost:5156/editor/**
2. Click **Import JSON**
3. Load `workflow.json`
4. Click **Deploy**

> 💡 In the visual editor, nodes with `HumanApproval: true` show a lock icon.
> Click the node to approve it when the workflow reaches that stage.
