# ⚡ 10-Minute Quickstart

Go from zero to running AI agent workflows. No fluff — just commands and results.

**Prerequisites:** [Docker](https://docs.docker.com/get-docker/) and [Python 3.9+](https://www.python.org/downloads/)

---

## 🟢 Step 1: Start Flint (2 minutes)

```bash
git clone https://github.com/flintai/flint.git
cd flint
docker compose -f docker-compose.dev.yml up -d
```

Verify it's running:

```bash
curl http://localhost:5156/health
```

```
OK
```

> Dev mode uses in-memory queue and store — no Redis, no Postgres, no config needed.

---

## 🟢 Step 2: Submit Your First Task (1 minute)

```bash
curl -X POST http://localhost:5156/tasks \
  -H "Content-Type: application/json" \
  -d '{"agent": "dummy", "prompt": "Hello Flint!"}'
```

```json
{
  "taskId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "state": "Queued"
}
```

Copy the `taskId` and check its status:

```bash
curl http://localhost:5156/tasks/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

```json
{
  "taskId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "state": "Succeeded",
  "result": "[dummy] processed prompt: Hello Flint!"
}
```

The `dummy` agent echoes your prompt back — it's built-in for testing.

---

## 🟢 Step 3: Install the Python SDK (1 minute)

```bash
pip install flint-ai
```

Create `hello.py`:

```python
from flint_ai.client import FlintClient

client = FlintClient("http://localhost:5156")

task = client.submit_task(agent="dummy", prompt="Hello from Python!")
result = client.wait_for_task(task.id)
print(result.output)
```

Run it:

```bash
python hello.py
```

```
[dummy] processed prompt: Hello from Python!
```

---

## 🟢 Step 4: Build a Workflow (3 minutes)

Workflows chain tasks into a DAG — each node runs after its dependencies complete.

Create `workflow.py`:

```python
from flint_ai.client import FlintClient
from flint_ai.workflow_builder import Workflow, Node

client = FlintClient("http://localhost:5156")

wf = (Workflow("my-first-workflow")
    .add(Node("step1", agent="dummy", prompt="Generate an idea"))
    .add(Node("step2", agent="dummy", prompt="Expand the idea", depends_on=["step1"]))
    .add(Node("step3", agent="dummy", prompt="Write the summary", depends_on=["step2"]))
    .build())

client.create_workflow(wf)
run = client.start_workflow("my-first-workflow")
print(f"Workflow started! ID: {run.id}")
```

Run it:

```bash
python workflow.py
```

```
Workflow started! ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Check node status:

```bash
curl http://localhost:5156/workflows/my-first-workflow/nodes
```

```json
[
  { "id": "step1", "state": "Succeeded" },
  { "id": "step2", "state": "Succeeded" },
  { "id": "step3", "state": "Succeeded" }
]
```

`step1` runs first, then `step2`, then `step3` — each waits for its dependency.

---

## 🟢 Step 5: Open the Dashboard (1 minute)

Open these in your browser:

| URL | What You Get |
|-----|-------------|
| [http://localhost:5156/dashboard/](http://localhost:5156/dashboard/) | Live metrics — tasks, queues, agents |
| [http://localhost:5156/editor/](http://localhost:5156/editor/) | Drag-and-drop DAG workflow builder |

The dashboard shows real-time task throughput, agent concurrency, and workflow state. The editor lets you visually wire up nodes without writing code.

---

## 🟢 Step 6: What's Next?

| Resource | Link |
|----------|------|
| Demo scripts | [`examples/demos/`](../examples/demos/) |
| Python SDK docs | [Python SDK Reference](../docs-site/python-sdk.md) |
| TypeScript SDK | [TypeScript SDK Reference](../docs-site/typescript-sdk.md) |
| C# SDK & examples | [SDKs & Examples](SDKsExamples.md) |
| API reference | [http://localhost:5156/swagger](http://localhost:5156/swagger) |
| Configuration | [Environment Variables](ENV_VARS.md) |

---

🎉 **You just built your first AI agent workflow in under 10 minutes.**

Three tasks, chained into a DAG, orchestrated by Flint. From here you can swap `"dummy"` for `"openai"`, `"claude"`, or `"copilot"` — just set the API key as an environment variable and you're running real agents.
