---
title: "Building an AI Code Review Pipeline with DAG Workflows"
description: "A step-by-step tutorial for building a multi-agent code review pipeline with human approval gates, dead letter queues, and real-time monitoring."
author: "Flint Team"
date: 2025-02-12
tags: [ai-agents, code-review, dag-workflows, tutorial, devops]
canonical_url: ""
series: "Production AI Infrastructure"
---

# Building an AI Code Review Pipeline with DAG Workflows

Code review is one of the best use cases for AI agents — it's repetitive, pattern-based, and benefits from multiple perspectives. But a real code review pipeline isn't just "send code to GPT." It's a multi-step process: generate analysis, run linters, execute tests, get human sign-off, then deploy.

This tutorial builds that pipeline from scratch using DAG (Directed Acyclic Graph) workflows. By the end, you'll have a working pipeline where AI agents handle the heavy lifting, a human reviewer approves the final result, and failures route to a dead letter queue instead of silently vanishing.

## The Pipeline

Here's what we're building:

```
┌──────────┐    ┌──────┐    ┌──────┐    ┌──────────────┐    ┌────────┐
│ generate │───▶│ lint │───▶│ test │───▶│ human-review │───▶│ deploy │
└──────────┘    └──────┘    └──────┘    └──────────────┘    └────────┘
     │               │           │              │                │
     ▼               ▼           ▼              ▼                ▼
   [DLQ]           [DLQ]      [DLQ]      [DLQ on reject]     [DLQ]
```

Each node is an AI agent task. Each arrow is a dependency edge. Every node has a dead letter queue fallback. The "human-review" node pauses the pipeline until a human approves or rejects.

## Prerequisites

Start the orchestrator in dev mode:

```bash
docker compose -f docker-compose.dev.yml up -d
```

Install the Python SDK:

```bash
pip install flint-ai
```

## Step 1: Define the Workflow

The Python SDK provides a fluent builder DSL for defining DAG workflows. Each `Node` declares its agent type, prompt template, retry policy, and dependencies.

```python
from flint_ai import Workflow, Node

pipeline = (
    Workflow("code-review-pipeline")

    # Step 1: AI generates a code review analysis
    .add(Node("generate", agent="openai",
              prompt=(
                  "You are a senior code reviewer. Analyze this pull request "
                  "diff and provide:\n"
                  "1. A summary of changes\n"
                  "2. Potential bugs or security issues\n"
                  "3. Suggestions for improvement\n"
                  "4. An overall quality score (1-10)\n\n"
                  "Diff:\n{diff}"
              ))
         .with_retries(3)
         .dead_letter_on_failure())

    # Step 2: Run static analysis on the generated review
    .add(Node("lint", agent="openai",
              prompt=(
                  "Review this code analysis for accuracy and completeness. "
                  "Flag any incorrect claims or missed issues. "
                  "Return a corrected review if needed.\n\n"
                  "Original review:\n{previous_output}"
              ))
         .depends_on("generate")
         .with_retries(2)
         .dead_letter_on_failure())

    # Step 3: Validate that suggested fixes don't break tests
    .add(Node("test", agent="openai",
              prompt=(
                  "Given this code review, identify any suggested changes "
                  "that could introduce regressions. For each suggestion, "
                  "describe what tests should be added or updated.\n\n"
                  "Review:\n{previous_output}"
              ))
         .depends_on("lint")
         .with_retries(3)
         .dead_letter_on_failure())

    # Step 4: Human approval gate
    .add(Node("human-review", agent="dummy",
              prompt="Awaiting human approval of the AI code review.")
         .depends_on("test")
         .requires_approval()
         .dead_letter_on_failure())

    # Step 5: Deploy / post the review
    .add(Node("deploy", agent="openai",
              prompt=(
                  "Format this approved code review as a GitHub PR comment "
                  "in markdown. Include the summary, issues found, "
                  "suggestions, and quality score.\n\n"
                  "Approved review:\n{previous_output}"
              ))
         .depends_on("human-review")
         .with_retries(2)
         .dead_letter_on_failure())

    .build()
)
```

Let's break down what the builder does:

- **`Workflow("code-review-pipeline")`** — Creates a named workflow definition.
- **`Node(id, agent, prompt)`** — Defines a task node with an agent type and prompt template. The `{diff}` and `{previous_output}` are placeholders resolved at runtime.
- **`.depends_on("generate")`** — Declares that this node runs only after "generate" succeeds. This creates the DAG edges.
- **`.with_retries(3)`** — On failure, retry up to 3 times with exponential backoff (2^attempt seconds + random jitter).
- **`.dead_letter_on_failure()`** — After exhausting retries, route to the DLQ instead of silently failing.
- **`.requires_approval()`** — Pause the workflow here. Execution continues only after explicit human approval.

## Step 2: Register and Start the Workflow

```python
import asyncio
from flint_ai import AsyncOrchestratorClient

async def main():
    async with AsyncOrchestratorClient("http://localhost:5156") as client:
        # Register the workflow definition
        await client.register_workflow(pipeline)

        # Start execution — the orchestrator enqueues the root node
        await client.start_workflow("code-review-pipeline")
        print("Pipeline started! Monitor at /dashboard/workflows")

asyncio.run(main())
```

When you call `start_workflow`, the orchestrator identifies entry nodes (nodes with no incoming edges — in this case, "generate") and enqueues them as tasks. Workers pick them up and execute them. As each node succeeds, the workflow engine enqueues downstream nodes automatically.

## Step 3: Human Approval Gates

When the pipeline reaches "human-review", it pauses. The task enters a waiting state, and no downstream nodes execute. This is intentional — you want a human to verify the AI's review before it gets posted.

### Why Approval Gates Matter

AI code reviews can be wrong. They hallucinate bugs that don't exist, miss real issues, and sometimes suggest changes that would break the codebase. A human gate between "AI analysis" and "post the review publicly" prevents embarrassing or harmful automation.

### Approving or Rejecting

Check pending approvals via the dashboard:

```bash
# List workflow node states
curl http://localhost:5156/dashboard/workflows/code-review-pipeline/nodes
```

Approve the node to continue the pipeline:

```bash
# Approve — enqueues the "deploy" node
curl -X POST http://localhost:5156/workflows/code-review-pipeline/nodes/human-review/approve
```

Or reject to stop the pipeline and route to the DLQ:

```bash
# Reject — marks as dead-lettered, "deploy" never runs
curl -X POST http://localhost:5156/workflows/code-review-pipeline/nodes/human-review/reject
```

Rejection doesn't lose the work. The task and its context land in the dead letter queue, where you can inspect what went wrong and decide whether to retry manually.

## Step 4: Dead Letter Queues for Failure Handling

Every node in our pipeline has `.dead_letter_on_failure()` set. Here's what happens when a node fails:

1. **First failure** — The worker catches the exception and re-enqueues the task.
2. **Retries 2 and 3** — Same thing, with exponential backoff (2s, 4s + jitter).
3. **After max retries** — The task moves to `DeadLetter` state.

Dead-lettered tasks are not lost. They're persisted with their full context: the prompt, the agent type, the error message, and the number of attempts.

```bash
# Inspect dead-lettered tasks
curl http://localhost:5156/dashboard/dlq
```

Example response:

```json
[
  {
    "id": "a1b2c3d4-...",
    "state": "DeadLetter",
    "agentType": "openai",
    "prompt": "You are a senior code reviewer...",
    "result": "Error: 429 Too Many Requests (after 3 retries)",
    "workflowId": "code-review-pipeline",
    "nodeId": "generate"
  }
]
```

From here, you can fix the root cause (upgrade your API plan, adjust concurrency limits) and manually re-submit the task.

## Step 5: Monitoring the Pipeline

### Prometheus Metrics

The orchestrator exposes Prometheus metrics at `GET /metrics`:

```
# Queue depth — how many tasks are waiting
aqo_queue_length 3

# Per-agent concurrency
aqo_concurrency_limit{agent="openai"} 5
aqo_concurrency_current{agent="openai"} 2

# Task outcomes
aqo_tasks_processed_total{status="succeeded"} 412
aqo_tasks_processed_total{status="failed"} 8
aqo_tasks_processed_total{status="dead_letter"} 2
```

### Workflow Dashboard

The dashboard endpoints give you a real-time view of workflow progress:

```bash
# All workflows and their status
curl http://localhost:5156/dashboard/workflows

# Specific workflow — node-by-node status
curl http://localhost:5156/dashboard/workflows/code-review-pipeline/nodes
```

### Real-Time Task Streaming

For individual tasks, you can stream updates via SSE or WebSocket:

```bash
# SSE stream — get live state changes
curl -N http://localhost:5156/tasks/{task-id}/stream
```

```
event: update
data: {"id":"...","state":"Running"}

event: update
data: {"id":"...","state":"Succeeded","result":"..."}

event: complete
data: {"id":"...","state":"Succeeded"}
```

## The Full Working Example

Here's everything in one script:

```python
"""
AI Code Review Pipeline — complete working example.
Requires: pip install flint-ai
Requires: docker compose -f docker-compose.dev.yml up -d
"""
import asyncio
from flint_ai import (
    AsyncOrchestratorClient,
    Workflow,
    Node,
)

# Define the pipeline
pipeline = (
    Workflow("code-review-pipeline")
    .add(Node("generate", agent="openai",
              prompt="Analyze this PR diff and provide a code review:\n\n{diff}")
         .with_retries(3)
         .dead_letter_on_failure())
    .add(Node("lint", agent="openai",
              prompt="Verify this review for accuracy:\n\n{previous_output}")
         .depends_on("generate")
         .with_retries(2)
         .dead_letter_on_failure())
    .add(Node("test", agent="openai",
              prompt="Check for regression risks:\n\n{previous_output}")
         .depends_on("lint")
         .with_retries(3)
         .dead_letter_on_failure())
    .add(Node("human-review", agent="dummy",
              prompt="Awaiting human approval.")
         .depends_on("test")
         .requires_approval()
         .dead_letter_on_failure())
    .add(Node("deploy", agent="openai",
              prompt="Format as a GitHub PR comment:\n\n{previous_output}")
         .depends_on("human-review")
         .with_retries(2)
         .dead_letter_on_failure())
    .build()
)

async def main():
    async with AsyncOrchestratorClient("http://localhost:5156") as client:
        # Register and start
        await client.register_workflow(pipeline)
        await client.start_workflow("code-review-pipeline")

        print("Pipeline started!")
        print("Monitor: http://localhost:5156/dashboard/workflows")
        print("Metrics: http://localhost:5156/metrics")
        print()
        print("When human-review is reached, approve with:")
        print("  curl -X POST http://localhost:5156/workflows/"
              "code-review-pipeline/nodes/human-review/approve")

if __name__ == "__main__":
    asyncio.run(main())
```

## Extending the Pipeline

This pattern scales to more complex workflows:

- **Fan-out**: Add parallel review nodes (e.g., security review + style review + performance review) that all depend on "generate" and fan back into a merge node.
- **Conditional edges**: Route different types of changes to different reviewers based on file paths or change size.
- **Multi-model ensemble**: Run the same review through OpenAI, Claude, and a fine-tuned model, then merge their outputs.
- **Webhook integration**: Configure `TASK_COMPLETION_WEBHOOK_URL` to POST results to Slack or your CI/CD system when the pipeline completes.

The DAG engine handles all the scheduling, dependency resolution, and failure isolation. You focus on what each agent does, not how they coordinate.

---

*This is Part 3 of the Production AI Infrastructure series. Start with [Part 1: Why Your AI Agents Need a Queue](01-why-ai-agents-need-a-queue.md) for the fundamentals, or check out the [quickstart guide](../docs-site/getting-started.md) to start building.*
