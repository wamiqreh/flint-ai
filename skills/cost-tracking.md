# Skill: Cost Tracking & Tool Logging

> Experimental — API may change.

## Overview

Flint tracks token usage, USD cost, and every tool call for OpenAI adapters.

## Key Files

| File | Purpose |
|------|---------|
| `flint_ai/adapters/core/cost_tracker.py` | FlintCostTracker, TimeBoundPrice |
| `flint_ai/adapters/core/types.py` | CostBreakdown, ToolExecution (dataclass) |
| `flint_ai/adapters/core/sanitization.py` | Input sanitization for logging |
| `flint_ai/adapters/openai/agent.py` | OpenAI adapter with cost integration |
| `flint_ai/server/engine/__init__.py` | ToolExecution (Pydantic model) |
| `flint_ai/server/engine/task_engine.py` | Persists tool executions |
| `flint_ai/server/store/__init__.py` | BaseToolExecutionStore ABC |
| `flint_ai/server/store/memory.py` | InMemoryToolExecutionStore |
| `flint_ai/server/store/postgres.py` | PostgresToolExecutionStore + migrations V5-V7 |
| `flint_ai/server/api/dashboard.py` | Cost + tool API endpoints |
| `flint_ai/server/ui/src/pages/CostsPage.tsx` | Costs UI |
| `flint_ai/server/ui/src/pages/ToolTracePage.tsx` | Tool trace UI |
| `flint_ai/server/ui/src/pages/RunsPage.tsx` | Workflow runs with DAG |

## CostTracker Usage

```python
from flint_ai.adapters.core.cost_tracker import FlintCostTracker, TimeBoundPrice
from datetime import datetime, timezone

tracker = FlintCostTracker()  # Has hardcoded OpenAI defaults

# Add time-bound pricing (old costs stay correct when prices change)
tracker.add_time_bound_price(TimeBoundPrice(
    model="gpt-4o-mini",
    prompt_cost_per_million=0.150,
    completion_cost_per_million=0.600,
    effective_from=datetime(2024, 7, 18, tzinfo=timezone.utc),
    effective_to=None,  # None = still active
))

# Calculate cost
cb = tracker.calculate("gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
print(cb.total_cost_usd)  # 0.00075
```

## Agent Integration

```python
agent = FlintOpenAIAgent(
    name="my-agent",
    model="gpt-4o-mini",
    tools=[my_tool],
    cost_tracker=tracker,  # Optional, defaults to FlintCostTracker()
)
result = await agent.safe_run({"prompt": "Hello"})
print(result.cost.total_cost_usd)
print(result.metadata["tool_executions"])  # List of tool call records
```

## DB Migrations

- **V5**: `flint_model_pricing` table (time-bound, multiple prices per model)
- **V6**: `flint_tool_executions` table
- **V7**: Fix model pricing PK to support time-bound entries

## Dashboard API

| Endpoint | Returns |
|----------|---------|
| `GET /dashboard/cost/summary` | Total cost, by model, by agent |
| `GET /dashboard/cost/task/{id}` | Per-task cost breakdown |
| `GET /dashboard/cost/workflow/{id}` | Per-node cost aggregation |
| `GET /dashboard/cost/timeline` | Hourly cost buckets |
| `GET /dashboard/tools/executions` | Tool call list (filterable) |
| `GET /dashboard/tools/errors` | Failed tool calls with stack traces |
| `GET /dashboard/tools/stats` | Aggregate tool statistics |

## Important

- Cost is computed at execution time and snapshotted in task metadata
- Time-bound pricing ensures old tasks keep their original cost even if prices change
- Tool executions are persisted via TaskEngine on success
- External workers report tool_executions in their result metadata
