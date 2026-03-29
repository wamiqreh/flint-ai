# 🚀 Flint Demo Workflows

Ready-to-run examples showcasing Flint's AI agent orchestration capabilities.

| Demo | Pattern | Agents | Key Features |
|------|---------|--------|--------------|
| [Code Review Pipeline](./code-review-pipeline/) | Sequential chain | 3 | Linear DAG, prompt chaining |
| [Document Summarizer](./document-summarizer/) | Fan-out / fan-in | 5 | Parallel execution, map-reduce |
| [Research Agent Team](./research-agent-team/) | Complex DAG | 5 | Parallel branches, human-in-the-loop approval gates |

## Quick Start

```bash
# 1. Start Flint
docker compose -f docker-compose.dev.yml up -d

# 2. Install the Python SDK
pip install flint-ai

# 3. Run any demo
cd examples/demos/code-review-pipeline
python workflow.py
```

All demos use the `dummy` agent so they work out of the box — no API keys needed.
Swap `"dummy"` for `"openai"` or `"claude"` when you're ready to use real LLMs.

## Visual Editor

Every demo includes a `workflow.json` you can import into the Flint visual editor:

1. Open **http://localhost:5156/editor/**
2. Click **Import JSON**
3. Load the `workflow.json` from any demo folder
4. Click **Deploy** to run it
