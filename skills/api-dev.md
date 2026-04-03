# Skill: API Development

Load when: adding endpoints, modifying routes, working on dashboard, HTTP API changes.

## App Factory

`flint_ai/server/app.py` — Central wiring point. All routes registered here.

## Route Files

| File | Prefix | Purpose |
|------|--------|---------|
| `flint_ai/server/api/workers.py` | `/tasks` | Claim, report result, heartbeat |
| `flint_ai/server/api/workflows.py` | `/workflows` | Register, run, approve/reject nodes |
| `flint_ai/server/api/dashboard.py` | `/dashboard` | Summary, DLQ, approvals |
| `flint_ai/server/api/__init__.py` | — | Route registration + approval/reject helpers |

## Adding a New Endpoint

### 1. Create or edit route file
```python
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/my-feature", tags=["my-feature"])

@router.get("/{item_id}")
async def get_item(item_id: str):
    item = await store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item

@router.post("/")
async def create_item(data: ItemCreate):
    record = await store.create(data)
    return {"id": record.id}
```

### 2. Register in app.py
```python
from flint_ai.server.api.my_feature import router as my_feature_router

app.include_router(my_feature_router)
```

## Existing Endpoints

### Workers (`/tasks`)
| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| POST | `/tasks/claim` | `claim_task()` | Worker claims a task (CAS) |
| POST | `/tasks/{task_id}/result` | `report_result()` | Report success/failure |
| POST | `/tasks/{task_id}/heartbeat` | `heartbeat()` | Keep lease alive (15s) |

### Workflows (`/workflows`)
| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| POST | `/workflows` | `register_workflow()` | Save workflow definition |
| GET | `/workflows` | `list_workflows()` | List all definitions |
| POST | `/workflows/runs` | `start_workflow_run()` | Start a run |
| GET | `/workflows/runs/{run_id}` | `get_run()` | Get run status |
| POST | `/workflows/runs/{run_id}/nodes/{node_id}/approve` | `approve_node()` | Approve DAG node |
| POST | `/workflows/runs/{run_id}/nodes/{node_id}/reject` | `reject_node()` | Reject DAG node |

### Dashboard (`/dashboard`)
| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| GET | `/dashboard/summary` | `get_summary()` | Task counts, queue depth, DLQ, workers |
| GET | `/dashboard/concurrency` | `get_concurrency()` | Per-agent concurrency usage |
| GET | `/dashboard/dlq` | `get_dlq()` | List DLQ messages |
| POST | `/dashboard/dlq/{message_id}/retry` | `retry_dlq()` | Retry DLQ message |
| POST | `/dashboard/dlq/purge` | `purge_dlq()` | Purge all DLQ |
| GET | `/dashboard/approvals` | `get_approvals()` | List pending approvals |

### Probes
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check (queue + store connectivity) |
| GET | `/ready` | Readiness probe (503 if deps down) |
| GET | `/live` | Liveness probe (always 200) |
| GET | `/metrics` | Prometheus metrics |

## Request/Response Patterns

### Error Response
```python
raise HTTPException(status_code=404, detail="Task not found")
raise HTTPException(status_code=400, detail="Invalid state transition")
raise HTTPException(status_code=409, detail="Task already claimed")
```

### Success Response
```python
return {"task_id": task_id, "state": "QUEUED"}
return JSONResponse(content={"status": "ok"}, status_code=201)
```

### No Content
```python
return Response(status_code=204)  # No tasks available
```

## Middleware

Registered in `app.py`:
- **Circuit breaker** — Protects queue/store connections
- **CORS** — Configurable origins
- **Request correlation ID** — Tracked across all operations

## Dashboard UI

- React SPA served from `flint_ai/server/static/`
- Built separately (not in repo)
- FastAPI serves static files with SPA fallback:
```python
@app.get("/ui/{path:path}")
async def serve_ui(path: str):
    # Try specific file, fallback to index.html
```

## Adding Dashboard Metrics

```python
from prometheus_client import Counter, Histogram

MY_COUNTER = Counter("flint_my_feature_total", "Total my feature operations")
MY_HISTOGRAM = Histogram("flint_my_feature_duration", "Duration of my feature")

# In endpoint:
MY_COUNTER.inc()
with MY_HISTOGRAM.time():
    result = await do_something()
```

## Validation

- Pydantic models for request/response bodies
- Input validation in `flint_ai/server/validators.py`
- Correlation IDs tracked via `flint_ai/server/correlation.py`

## Testing API Endpoints

```python
from httpx import AsyncClient

async def test_my_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/my-feature/", json={"name": "test"})
        assert response.status_code == 201
        assert response.json()["name"] == "test"
```

## Important

- All endpoints are async
- Use `HTTPException` for errors, not plain exceptions
- Correlation IDs are auto-generated and logged
- Circuit breaker protects backend connections — if tripped, endpoints return 503
- Static UI files served with SPA fallback routing
