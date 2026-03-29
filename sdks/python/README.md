# Flint

[![PyPI version](https://img.shields.io/pypi/v/flint-ai)](https://pypi.org/project/flint-ai/)
[![Python versions](https://img.shields.io/pypi/pyversions/flint-ai)](https://pypi.org/project/flint-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

> Python SDK for submitting AI agent tasks, building DAG workflows, and orchestrating execution at scale.

## Features

- **Async & sync clients** — first-class `asyncio` support with a synchronous wrapper
- **Automatic retries** — exponential backoff with jitter for transient failures (429, 502–504)
- **Batch submission** — submit many tasks concurrently in a single call
- **DAG workflow builder** — fluent DSL with cycle detection and dependency validation
- **SSE streaming** — real-time task updates via Server-Sent Events
- **CLI** — submit tasks, check status, and manage workflows from the terminal
- **LangChain integration** — drop-in `Runnable` adapter for LangChain pipelines
- **Typed models** — Pydantic v2 models with full type annotations

## Installation

```bash
pip install flint-ai
```

With optional extras:

```bash
pip install flint-ai[cli]        # Typer-based CLI
pip install flint-ai[langchain]   # LangChain adapter
```

## Quick Start

```python
import asyncio
from flint_ai import AsyncOrchestratorClient

async def main():
    async with AsyncOrchestratorClient("http://localhost:5156") as client:
        task_id = await client.submit_task("openai", "Summarise this document")
        task = await client.wait_for_task(task_id)
        print(task.state, task.result)

asyncio.run(main())
```

## Workflow Builder

Chain agent tasks into validated DAG workflows:

```python
from flint_ai import Workflow, Node

workflow = (
    Workflow("code-review")
    .add(Node("generate", agent="openai", prompt="Write code for {task}"))
    .add(Node("lint", agent="dummy", prompt="Lint the output").depends_on("generate"))
    .add(Node("review", agent="claude", prompt="Review the code").depends_on("lint"))
    .build()  # validates: no cycles, no dangling refs, no duplicate IDs
)
```

Nodes support `.with_retries(n)`, `.requires_approval()`, `.dead_letter_on_failure()`, and `.with_metadata(...)`.

## CLI

```bash
# Submit a task
flint submit --agent openai --prompt "Hello world"

# Check status
flint status <task-id>

# Workflow management
flint workflows list
flint workflows start <workflow-id>
```

Install the CLI extra: `pip install flint-ai[cli]`

## Batch Submission

```python
from flint_ai import AsyncOrchestratorClient, TaskSubmission

async with AsyncOrchestratorClient("http://localhost:5156") as client:
    ids = await client.submit_tasks([
        TaskSubmission(agent_type="openai", prompt="Task 1"),
        TaskSubmission(agent_type="openai", prompt="Task 2"),
    ])
```

## Error Handling

The SDK raises typed exceptions for common failure modes:

| Exception | Trigger |
|-----------|---------|
| `TaskNotFoundError` | HTTP 404 |
| `RateLimitError` | HTTP 429 (includes `retry_after`) |
| `AuthenticationError` | HTTP 401 / 403 |
| `WorkflowValidationError` | HTTP 422 |
| `ConnectionError` | Network / timeout failures |

All inherit from `OrchestratorError`.

## Documentation

Full documentation and examples:

- [Examples](https://github.com/flint-ai/flint-ai/tree/main/sdks/python/examples)
- [Notebooks](https://github.com/flint-ai/flint-ai/tree/main/sdks/python/notebooks)
- [Changelog](https://github.com/flint-ai/flint-ai/blob/main/sdks/python/CHANGELOG.md)

## License

[MIT](./LICENSE)
