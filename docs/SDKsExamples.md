SDKs & Examples

C# example (submit a task via HTTP to the API):

```csharp
// using Orchestrator.Api.Client (example)
var client = new OrchestratorClient(new Uri("http://localhost:5000"));
var task = new SubmitTaskRequest { Prompt = "Write a C# function that reverses a string", Metadata = { ["language"] = "C#" } };
var response = await client.SubmitTaskAsync(task);
Console.WriteLine($"Submitted task: {response.TaskId}");
```

Python minimal example (HTTP):

```python
import requests

def submit(prompt: str):
    payload = {"prompt": prompt, "metadata": {"language": "python"}}
    r = requests.post("http://localhost:5000/api/tasks/submit", json=payload)
    r.raise_for_status()
    data = r.json()
    print("Submitted", data.get("taskId"))

if __name__ == '__main__':
    submit("Write a Python function that validates email addresses")
```

Notes:
- The repo includes a lightweight in-memory SDK surface (examples only). For production use, configure credentials via environment variables (e.g., COPILOT_API_KEY, CLAUDE_API_KEY) and enable streaming by setting ENABLE_AGENT_STREAMING=true.
- When integrating coding agents, always ensure API keys are stored securely (Azure KeyVault, AWS Secrets Manager, etc.) and not committed to source control.

---

## Python SDK (flint_ai)

Location: `sdks/python`

Install:

```bash
cd sdks/python
pip install .
```

Install with CLI:

```bash
pip install .[cli]
```

Async client example:

```python
import asyncio
from flint_ai import AsyncOrchestratorClient

async def main():
    client = AsyncOrchestratorClient("http://localhost:5156")
    task_id = await client.submit_task("dummy", "Echo hello from SDK")
    task = await client.wait_for_task(task_id)
    print(task.model_dump())
    await client.close()

asyncio.run(main())
```

CLI examples:

```bash
flint submit --agent dummy --prompt "hello"
flint status <task-id>
flint workflows list
flint workflows start <workflow-id>
```
