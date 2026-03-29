---
title: "Why Your AI Agents Need a Queue (And What Happens When They Don't)"
description: "Rate limits, lost tasks, and silent failures — here's why queue-based orchestration is essential for running AI agents in production."
author: "Flint Team"
date: 2025-01-15
tags: [ai-agents, queues, production, reliability, llm-ops]
canonical_url: ""
series: "Production AI Infrastructure"
---

# Why Your AI Agents Need a Queue (And What Happens When They Don't)

You shipped your AI feature on Friday. By Monday morning, your inbox is full of bug reports: half the requests timed out, a third hit rate limits, and a handful just vanished into the void. Sound familiar?

Running AI agents directly against LLM APIs feels fine during development. You fire off a request, get a response, and move on. But in production — where dozens of users hit your endpoint at once, where OpenAI's rate limits kick in at the worst possible moment, where a single network hiccup can drop a task with no trace — the cracks show fast.

This post explains why a queue-based architecture is the missing piece between your AI agents and production reliability.

## The Five Ways Unqueued AI Agents Fail

### 1. Rate Limits Become Brick Walls

Every LLM provider enforces rate limits. OpenAI, Anthropic, and Azure all cap requests per minute and tokens per minute. When you fire requests directly from your application code, a traffic spike means a cascade of `429 Too Many Requests` errors. Worse, many retry implementations don't honor the `Retry-After` header, so they hammer the API again immediately — making the problem worse.

### 2. Failures Are Silent and Permanent

A raw `HttpClient.PostAsync()` call either succeeds or throws. If it throws, what happens? In most codebases: the exception gets logged, the user sees a 500 error, and the task is gone forever. There's no automatic retry, no record of what failed, and no way to replay it.

### 3. No Visibility Into What's Happening

How many agent tasks are running right now? How many are waiting? What's the average latency? Without a queue, you're flying blind. You can't answer these questions without instrumenting every call site individually.

### 4. Concurrency Is Uncontrolled

If 50 users trigger an AI agent at the same time, you send 50 concurrent requests to the LLM API. This burns through rate limits instantly, can overwhelm your own infrastructure, and provides no way to prioritize important tasks over background ones.

### 5. Multi-Step Workflows Collapse

Many real AI workflows involve chains: generate text → check quality → apply edits → summarize. When step 2 fails in an unqueued setup, the entire chain halts with no way to retry just the failed step or skip to the next one.

## The Pattern: Queue-Based Agent Orchestration

The fix isn't complicated conceptually. Instead of calling LLM APIs inline with your request handler, you **submit tasks to a durable queue** and let **workers** process them independently.

```
┌──────────┐     ┌───────────┐     ┌──────────┐     ┌─────────┐
│  Your App │────▶│   Queue   │────▶│  Worker  │────▶│ LLM API │
└──────────┘     └───────────┘     └──────────┘     └─────────┘
                       │                 │
                       │           ┌─────▼──────┐
                       │           │  Retry w/   │
                       │           │  Backoff    │
                       │           └─────┬──────┘
                       │                 │
                  ┌────▼─────┐    ┌──────▼──────┐
                  │  Status  │    │ Dead Letter  │
                  │  Store   │    │   Queue      │
                  └──────────┘    └─────────────┘
```

This buys you:

- **Durability** — Tasks survive crashes. If the worker restarts, pending tasks are still in the queue.
- **Controlled concurrency** — Workers pull tasks at a rate the LLM API can handle, with per-agent semaphores limiting concurrent requests.
- **Automatic retries** — Failed tasks go back to the queue with exponential backoff. Rate-limited responses honor `Retry-After` headers.
- **Dead letter queues** — After exhausting retries, tasks land in a DLQ for inspection instead of vanishing.
- **Observability** — Queue length, processing time, success/failure rates — all measurable from one place.

## Before and After: A Code Comparison

### Before: Raw API Calls (Fragile)

```python
import httpx

async def summarize(text: str) -> str:
    """Breaks under load. No retries. No visibility."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": f"Summarize: {text}"}]
            },
            timeout=30.0
        )
        response.raise_for_status()  # 429? 500? Game over.
        return response.json()["choices"][0]["message"]["content"]
```

What goes wrong: no retry on rate limits, no concurrency control, no record of failure, no way to monitor throughput.

### After: Queue-Based with Retries

```python
from flint_ai import AsyncOrchestratorClient

async def summarize(text: str) -> str:
    """Durable. Retries automatically. Observable."""
    async with AsyncOrchestratorClient("http://localhost:5156") as client:
        task_id = await client.submit_task(
            agent_type="openai",
            prompt=f"Summarize: {text}"
        )
        result = await client.wait_for_task(task_id)
        return result.result
```

Behind the scenes, the orchestrator:

1. Enqueues the task in Redis Streams (durable, survives restarts)
2. A worker picks it up, respecting concurrency limits (default: 2 concurrent OpenAI calls)
3. On failure, Polly retries with exponential backoff (2^attempt + jitter, up to 5 attempts)
4. Rate-limited responses (`429`) parse the `Retry-After` header and wait the exact duration
5. After max retries, the task routes to a dead letter queue for manual inspection
6. Prometheus metrics track queue depth, success rate, and per-agent concurrency in real time

Your application code stays simple. The reliability lives in infrastructure.

## When Do You Actually Need This?

Not every project does. If you're building a single-user CLI tool that calls GPT once, a queue is overkill. But if any of these are true, you probably need one:

- **Multiple users** hitting AI endpoints concurrently
- **Background processing** — tasks that don't need to block the HTTP response
- **Multi-step pipelines** — chains of agent calls where failures need isolated handling
- **SLA requirements** — you can't afford to silently drop tasks
- **Cost control** — you need to limit how many concurrent API calls you're making

## Getting Started

Flint runs locally with zero external dependencies using in-memory mode:

```bash
# Clone and start
docker compose -f docker-compose.dev.yml up

# Submit a task
curl -X POST http://localhost:5156/tasks \
  -H "Content-Type: application/json" \
  -d '{"AgentType": "dummy", "Prompt": "Hello, world!"}'
```

For production, swap to Redis + PostgreSQL:

```bash
docker compose up  # Starts API, worker, Redis, PostgreSQL
```

The [quickstart guide](../docs-site/getting-started.md) walks through the full setup in under five minutes, including the Python SDK, workflow definitions, and monitoring.

## What's Next

In the next post, we'll look at how to add queue-based reliability **under an existing LangChain setup** — without rewriting your chains. If you've built a prototype with LangChain and need to harden it for production, that one's for you.

---

*Flint is open source. Check out the [repository](https://github.com/your-org/flint-ai) for docs, examples, and the Python SDK.*
