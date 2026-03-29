# template-rag-pipeline

A Retrieval-Augmented Generation (RAG) workflow template for
[Flint](https://github.com/your-org/flint-ai).

## Installation

```bash
flint plugins install template-rag-pipeline
```

## Overview

This template provides a 3-step RAG pipeline:

```
┌───────────┐     ┌──────────┐     ┌──────────┐
│ Retrieve  │────▶│ Generate │────▶│ Validate │
│ (context) │     │ (answer) │     │ (quality)│
└───────────┘     └──────────┘     └──────────┘
```

1. **Retrieve** — Fetches relevant documents/context for the query.
2. **Generate** — Produces an answer grounded in the retrieved context.
3. **Validate** — Checks the answer for accuracy and hallucination.

## Workflow Definition

The pipeline is defined in [`workflow.json`](workflow.json) using the standard
AQO `WorkflowDefinition` schema.

### Nodes

| Node | Agent | Purpose |
|------|-------|---------|
| `retrieve` | `openai` | Retrieve relevant context for the query |
| `generate` | `openai` | Generate a grounded answer from context |
| `validate` | `openai` | Validate answer quality and faithfulness |

### Customization

Edit `workflow.json` to:

- Change agent types (e.g. use `gemini` or `claude` instead of `openai`).
- Modify prompt templates for your domain.
- Add or remove pipeline stages.
- Enable `HumanApproval` on the validate step for critical workflows.

## Usage

### Import the Workflow

```python
import json
from flint_ai import AsyncOrchestratorClient

async def main():
    client = AsyncOrchestratorClient()

    with open("workflow.json") as f:
        workflow_data = json.load(f)

    from flint_ai.models import WorkflowDefinition
    workflow = WorkflowDefinition.model_validate(workflow_data)
    await client.create_workflow(workflow)
    await client.start_workflow(workflow.id)
```

### CLI

```bash
# Create the workflow on the server
curl -X POST http://localhost:5156/workflows \
  -H "Content-Type: application/json" \
  -d @workflow.json

# Start the workflow
flint workflows start rag-pipeline
```

## License

MIT
