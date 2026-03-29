# Flint

**The open-source task queue and workflow engine for AI agents.**

Submit tasks, chain them into DAG pipelines, add retries and human approval gates — all from Python or TypeScript. The server runs as a single Docker container; no .NET knowledge required.

---

## Get Started in 60 Seconds

```bash
# 1. Start the server (in-memory mode, zero dependencies)
docker compose -f docker-compose.dev.yml up -d

# 2. Install the Python SDK
pip install flint-ai

# 3. Run your first task
python -c "
from flint_ai import OrchestratorClient
client = OrchestratorClient()
task_id = client.submit_task('dummy', 'Hello, world!')
result = client.wait_for_task(task_id)
print(result.state, result.result)
"
```

That's it. You just submitted an AI agent task, waited for it to complete, and printed the result.

→ **[5-Minute Quickstart](getting-started.md)** for the full walkthrough.

---

## Why Flint?

Building AI apps is easy. Running them **reliably at scale** is hard. This project handles the hard parts so you can focus on your agent logic.

| Feature | What it does |
|---|---|
| **Agent-Agnostic** | Works with any AI provider — OpenAI, Claude, Copilot, or your own models |
| **DAG Workflows** | Chain tasks into multi-step pipelines with conditional edges |
| **Automatic Retries** | Exponential backoff with jitter, Retry-After header parsing, dead-letter queues |
| **Human Approval Gates** | Pause a workflow and wait for a human to approve or reject before continuing |
| **Pluggable Queues** | In-memory for dev, Redis Streams for production. Kafka & SQS adapters available |
| **Full Observability** | Prometheus `/metrics`, structured logging, OpenTelemetry tracing, live dashboard |
| **Streaming Updates** | SSE and WebSocket streams for real-time task state changes |

---

## Choose Your SDK

=== "Python"

    ```bash
    pip install flint-ai
    ```

    ```python
    from flint_ai import AsyncOrchestratorClient

    async with AsyncOrchestratorClient() as client:
        task_id = await client.submit_task("openai", "Summarize this document")
        result = await client.wait_for_task(task_id)
        print(result.result)
    ```

    → **[Python SDK Reference](python-sdk.md)**

=== "TypeScript"

    ```bash
    npm install @flint-ai/sdk
    ```

    ```typescript
    import { OrchestratorClient } from "@flint-ai/sdk";

    const client = new OrchestratorClient();
    const taskId = await client.submitTask("openai", "Summarize this document");
    const result = await client.waitForTask(taskId);
    console.log(result.result);
    ```

    → **[TypeScript SDK Reference](typescript-sdk.md)**

=== "curl"

    ```bash
    # Submit a task
    curl -X POST http://localhost:5156/tasks \
      -H "Content-Type: application/json" \
      -d '{"AgentType": "openai", "Prompt": "Summarize this document"}'

    # Check the result
    curl http://localhost:5156/tasks/{task_id}
    ```

---

## Documentation

| Page | Description |
|---|---|
| **[Quickstart](getting-started.md)** | Start the server & run your first workflow in 5 minutes |
| **[Python SDK](python-sdk.md)** | Full reference — client, workflows, CLI, LangChain adapter |
| **[TypeScript SDK](typescript-sdk.md)** | Full reference — client, workflows, streaming |
| **[Architecture](architecture.md)** | How the system works under the hood |
| **[Configuration](../docs/ENV_VARS.md)** | All environment variables and tuning options |
