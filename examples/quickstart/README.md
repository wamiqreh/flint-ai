# Quickstart Examples

Minimal, self-contained examples. Just run them.

## Prerequisites

```bash
pip install flint-ai[openai]
$env:OPENAI_API_KEY = "sk-..."
docker compose up -d    # PostgreSQL + Redis
```

## Embedded Mode (engine runs in your process)

| # | File | What | Time |
|---|------|------|------|
| 01 | `01_embedded_enqueue.py` | Start once, enqueue 3 workflows (Global engine style) | ~15s |
| 02 | `02_embedded_run_once.py` | Start engine, run 1 workflow, stop | ~5s |
| 03 | `03_sequential_pipeline.py` | A → B → C with data passing | ~10s |
| 04 | `04_fanout_fanin.py` | A → (B, C) → D parallel branches | ~10s |
| 05 | `05_approval_gate.py` | Workflow pauses for human approval | ~10s |

```bash
python examples/quickstart/01_embedded_enqueue.py
python examples/quickstart/02_embedded_run_once.py
python examples/quickstart/03_sequential_pipeline.py
python examples/quickstart/04_fanout_fanin.py
python examples/quickstart/05_approval_gate.py
```

## Server Mode (separate server + client worker)

| # | File | What | Time |
|---|------|------|------|
| 06 | `06_server_enqueue.py` | Start worker, enqueue multiple workflows | ~15s |
| 07 | `07_server_run_once.py` | Start worker, run 1 workflow, stop worker | ~5s |

```bash
# Terminal 1: start server (if not already running)
docker compose up -d
python -m flint_ai.server --port 5156 --redis redis://localhost:6379 --postgres postgresql://flint@localhost:5433/flint

# Terminal 2: run example
python examples/quickstart/06_server_enqueue.py
python examples/quickstart/07_server_run_once.py
```

## Key Patterns

### Run & Enqueue (Global engine style)
```python
configure_engine(agents=[agent])  # Start once
r1 = Workflow("task-1").add(Node("s", agent, prompt="...")).run()
r2 = Workflow("task-2").add(Node("s", agent, prompt="...")).run()
# ... from anywhere in your code
shutdown_engine()
```

### Run in One Go
```python
configure_engine(agents=[agent])
results = Workflow("task").add(Node("s", agent, prompt="...")).run()
shutdown_engine()
```

### Data Passing
```python
.add(Node("b", agent=writer, prompt="{a}").depends_on("a"))
```

### Fan-out
```python
.add(Node("c1", agent=w, prompt="{a}").depends_on("a"))
.add(Node("c2", agent=w, prompt="{a}").depends_on("a"))
.add(Node("d", agent=w, prompt="{c1}\n{c2}").depends_on("c1", "c2"))
```

### Approval Gate
```python
.add(Node("review", agent=r, prompt="{draft}")
     .depends_on("draft").requires_approval())
# run(on_approval=my_callback)
```

