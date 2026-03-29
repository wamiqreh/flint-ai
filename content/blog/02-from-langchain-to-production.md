---
title: "From LangChain Prototype to Production: Adding Reliability to AI Workflows"
description: "Your LangChain prototype works on your laptop. Here's how to make it survive production traffic with queues, retries, and observability."
author: "Flint Team"
date: 2025-01-29
tags: [langchain, production, reliability, queues, ai-workflows]
canonical_url: ""
series: "Production AI Infrastructure"
---

# From LangChain Prototype to Production: Adding Reliability to AI Workflows

Your LangChain prototype is impressive. It chains together an LLM call, a retrieval step, and a summarizer. It runs perfectly on your laptop with a single request at a time. Then you deploy it behind a FastAPI endpoint, and everything falls apart.

This isn't a LangChain problem — it's a production infrastructure problem. LangChain is a framework for composing LLM calls. It doesn't manage queues, retries, concurrency limits, or dead letter handling. That's a different layer entirely.

This post shows how to add that layer under your existing LangChain code without rewriting your chains.

## Where LangChain Prototypes Break in Production

### Rate Limits Hit Harder Than You Expect

In development, you send one request at a time. In production, 20 users hit your endpoint simultaneously. That's 20 concurrent OpenAI calls — and if your plan allows 60 RPM, you're rate-limited within seconds. LangChain doesn't queue or throttle these calls.

### Chain Failures Are All-or-Nothing

A LangChain chain with three steps (retrieve → generate → format) runs sequentially. If step 2 fails due to a transient API error, the entire chain throws an exception. There's no built-in retry for individual steps, no way to resume from the failed step, and no record of what succeeded before the failure.

### Timeouts Cascade

LLM calls can take 5–30 seconds. Under load, you run into connection pool exhaustion, HTTP client timeouts, and gateway timeouts — all of which surface as cryptic errors with no clear root cause.

### No Visibility

"How many chains are running? What's the failure rate for the summarize step? Which model is bottlenecking?" Without explicit instrumentation at every stage, you can't answer these questions.

## What Production AI Infrastructure Needs

Before diving into code, here's what the production layer needs to provide:

| Capability | Why |
|-----------|-----|
| **Task queue** | Decouple submission from execution; survive restarts |
| **Concurrency control** | Limit parallel LLM calls per provider |
| **Automatic retries** | Exponential backoff with jitter; honor `Retry-After` |
| **Dead letter queue** | Capture permanently failed tasks for inspection |
| **Observability** | Prometheus metrics, structured logs, OpenTelemetry traces |
| **Workflow orchestration** | Multi-step DAGs with conditional routing |

LangChain handles none of these. A queue orchestrator handles all of them.

## Adding AQO Under Your LangChain Setup

Flint provides a `LangChainOrchestratorRunnable` that wraps any LangChain chain as a queued, retried, observable task. It implements LangChain's `Runnable` interface, so it slots into existing LCEL (LangChain Expression Language) pipelines.

### Step 1: Install the SDK

```bash
pip install flint-ai
```

### Step 2: Wrap Your Chain

**Before — direct LangChain call:**

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_template("Summarize this text:\n\n{text}")
llm = ChatOpenAI(model="gpt-4o-mini")

# Fragile: no retries, no queue, no concurrency control
chain = prompt | llm
result = chain.invoke({"text": document})
```

**After — queued through AQO:**

```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from flint_ai import (
    AsyncOrchestratorClient,
    LangChainOrchestratorRunnable,
)

client = AsyncOrchestratorClient("http://localhost:5156")

# Same prompt, but execution goes through the orchestrator queue
runnable = LangChainOrchestratorRunnable(
    client=client,
    agent_type="openai",
)

# Use it like any LangChain Runnable
result = await runnable.ainvoke("Summarize this text:\n\n" + document)
```

The `LangChainOrchestratorRunnable` submits the prompt as a task to the orchestrator, which queues it in Redis Streams, executes it with concurrency limits and retry policies, and returns the result. Your LangChain code doesn't change structurally — it's still a Runnable.

### Step 3: Multi-Step Workflows

For chains with multiple steps, define a workflow with the Python DSL:

```python
from flint_ai import Workflow, Node, AsyncOrchestratorClient

async with AsyncOrchestratorClient("http://localhost:5156") as client:
    workflow = (
        Workflow("rag-pipeline")
        .add(Node("retrieve", agent="dummy",
                   prompt="Retrieve relevant documents for: {query}"))
        .add(Node("generate", agent="openai",
                   prompt="Answer based on context: {query}")
             .depends_on("retrieve")
             .with_retries(3))
        .add(Node("format", agent="openai",
                   prompt="Format the answer as markdown")
             .depends_on("generate")
             .with_retries(2))
        .build()
    )

    await client.register_workflow(workflow)
    await client.start_workflow("rag-pipeline")
```

Each node runs independently. If "generate" fails, only that step retries — "retrieve" doesn't re-run. If "generate" exhausts its retries, it routes to the dead letter queue while "retrieve"'s successful result remains intact.

## Architecture: Before and After

### Before: Inline LangChain

```
                    ┌─────────────────────────────────────┐
  HTTP Request ───▶ │  FastAPI Handler                     │
                    │                                      │
                    │  chain = prompt | llm | parser       │
                    │  result = chain.invoke(input)  ◀── BLOCKS 5-30s
                    │                                      │
                    │  return result                       │
                    └─────────────────────────────────────┘
                                     │
                              ┌──────▼──────┐
                              │  OpenAI API  │  ◀── rate limits,
                              └─────────────┘      timeouts, 500s
```

Problems: blocking request, no retry, no concurrency control, no task persistence.

### After: AQO-Backed LangChain

```
                    ┌──────────────────┐
  HTTP Request ───▶ │  FastAPI Handler  │
                    │                   │
                    │  task_id = submit │──▶ Returns immediately
                    │  return task_id   │
                    └──────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │    Redis Streams    │  Durable queue
                    │    (task queue)     │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Worker Process     │
                    │                     │
                    │  ┌───────────────┐  │
                    │  │ Semaphore     │  │  Concurrency: 2
                    │  │ (per agent)   │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────▼───────┐  │
                    │  │ Polly Retry   │  │  5 attempts,
                    │  │ (exp backoff) │  │  exponential backoff
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────▼───────┐  │
                    │  │ LLM API Call  │  │  OpenAI / Claude
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────▼───────┐  │
                    │  │ Save Result   │──┼──▶ PostgreSQL
                    │  └───────────────┘  │
                    └─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Dead Letter Queue  │  After max retries
                    └────────────────────┘
```

Your FastAPI handler returns immediately with a task ID. The client polls or streams for the result. The queue handles durability, the worker handles retries and concurrency, and Prometheus tracks everything.

## Configuration That Matters

Set these environment variables to tune production behavior:

```bash
# Concurrency: max 5 OpenAI calls, 3 Claude calls at once
CONCURRENCY_OPENAI=5
CONCURRENCY_CLAUDE=3

# Redis for durable queuing
REDIS_CONNECTION=redis:6379

# PostgreSQL for task persistence
DefaultConnection=Host=postgres;Database=orchestrator;Username=flint;Password=secret

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
```

Monitor with Prometheus at `GET /metrics`:

```
aqo_queue_length 12
aqo_concurrency_limit{agent="openai"} 5
aqo_concurrency_current{agent="openai"} 3
aqo_tasks_processed_total{status="succeeded"} 1847
aqo_tasks_processed_total{status="failed"} 23
```

## The Migration Path

You don't have to rewrite everything at once. Here's a practical migration:

1. **Start with the hot path.** Identify the LangChain call that fails most often (usually the primary LLM call) and route it through the orchestrator.
2. **Add observability first.** Even before retries, just having queue metrics and task history is a massive improvement.
3. **Move to workflows gradually.** Once individual calls are stable, define multi-step workflows for your chains.
4. **Keep LangChain for composition.** LangChain is good at prompt templating and chain composition. AQO handles execution reliability. They complement each other.

## What's Next

In the next post, we'll build a complete AI code review pipeline — a real-world multi-step workflow with DAG orchestration, human approval gates, and dead letter handling. If you want to see how these patterns work end-to-end, that's the one to read.

---

*Flint is open source. The Python SDK includes the LangChain adapter, workflow builder, and CLI. See the [quickstart guide](../docs-site/getting-started.md) to get running in five minutes.*
