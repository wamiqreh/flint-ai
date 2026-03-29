# agent-gemini

Google Gemini agent adapter for [Flint](https://github.com/your-org/flint-ai).

## Installation

```bash
flint plugins install agent-gemini
```

## Configuration

Set the following environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes | — | Google AI Studio API key |
| `GEMINI_MODEL` | No | `gemini-pro` | Model name (`gemini-pro`, `gemini-ultra`, etc.) |

Get your API key at [Google AI Studio](https://aistudio.google.com/apikey).

## Usage

Once installed, use `gemini` as the agent type:

### CLI

```bash
flint submit --agent gemini --prompt "Explain quantum computing"
```

### Python SDK

```python
from flint_ai import AsyncOrchestratorClient

async def main():
    client = AsyncOrchestratorClient()
    task_id = await client.submit_task("gemini", "Explain quantum computing")
    result = await client.wait_for_task(task_id)
    print(result.result)
```

### In a Workflow

```json
{
  "Id": "gemini-pipeline",
  "Nodes": [
    {
      "Id": "step-1",
      "AgentType": "gemini",
      "PromptTemplate": "Summarize the following: {{input}}"
    }
  ],
  "Edges": []
}
```

## Supported Models

- `gemini-pro` — Best for general text generation
- `gemini-ultra` — Most capable model for complex tasks
- `gemini-pro-vision` — Multimodal (text + images)

## License

MIT
