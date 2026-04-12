# Quickstart Examples

Minimal, self-contained examples (15-25 lines each). Each file runs independently.

## Examples

| File | What | API Key |
|------|------|---------|
| [`01_hello_workflow.py`](01_hello_workflow.py) | 3-node sequential pipeline | None |
| [`02_with_cost_tracking.py`](02_with_cost_tracking.py) | Same + automatic cost tracking | OpenAI |
| [`03_embedded_worker.py`](03_embedded_worker.py) | Embedded mode with custom worker settings | None |
| [`04_approval_gates.py`](04_approval_gates.py) | Human approval in workflow | None |
| [`05_parallel_branches.py`](05_parallel_branches.py) | Fan-out / fan-in pattern | None |

## Running

```bash
# No API key needed (most examples use dummy agents):
python examples/quickstart/01_hello_workflow.py
python examples/quickstart/03_embedded_worker.py
python examples/quickstart/04_approval_gates.py
python examples/quickstart/05_parallel_branches.py

# With OpenAI key:
$env:OPENAI_API_KEY = "sk-..."
python examples/quickstart/02_with_cost_tracking.py
```

## Key Concepts

### Cost Tracking
Cost tracking is **enabled by default**. No manual tracker needed:
```python
agent = FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini")
# Cost is auto-tracked — no cost_tracker= parameter needed
```

To disable: `FlintOpenAIAgent(..., enable_cost_tracking=False)`
To override pricing: `FlintOpenAIAgent(..., cost_config_override={"prompt": 5.0, "completion": 20.0})`

### Embedded Mode (Hangfire-like)
Embedded mode runs server + workers in one process:
```python
workflow.run(
    workers=2,           # Background worker count
    poll_interval=0.5,   # Queue poll interval (seconds)
    adapter_concurrency=10,  # Per-agent concurrency limit
)
```

## Next Steps
- [Advanced Examples](../advanced/) — Production scenarios, retries, error handling
- [OpenAI Examples](../openai/) — OpenAI-specific features
- [Usage Tracking](../usage_tracking/) — Unified cost tracking with events
