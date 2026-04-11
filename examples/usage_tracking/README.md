# Usage Tracking Examples

These examples demonstrate Flint AI's unified cost tracking system for monitoring and analyzing AI provider costs across different modalities (LLM calls, embeddings, images, audio).

## Quick Start

```bash
pip install -e ".[all]"
python examples/usage_tracking/embedding_image_costs.py
```

## Examples

### `embedding_image_costs.py` — Multimodal Cost Tracking ⭐
**What it shows:** How to calculate costs for different AI modalities using the unified `CostEngine`.

Features:
- **Text Embeddings**: text-embedding-3-small ($0.00002/1K) and text-embedding-3-large ($0.00013/1K)
- **Image Generation**: DALL-E 3 ($0.04-0.12 per image depending on size)
- **Vision Analysis**: GPT-4 Vision with image understanding
- **Event tracking**: Full cost breakdown and event emission

**Run it:**
```bash
python examples/usage_tracking/embedding_image_costs.py
```

**Output:**
```
✓ Embeddings (2 calls):        $0.000750
✓ Image generation (1 call):   $0.120000
✓ Vision analysis (1 call):    $0.010000
------
Total multimodal cost:          $0.130750
```

---

### `simple_llm.py` — Basic LLM Cost Tracking
**What it shows:** How to track costs for simple LLM calls using an adapter.

Requires: `OPENAI_API_KEY` environment variable

```bash
$env:OPENAI_API_KEY = "sk-..."
python examples/usage_tracking/simple_llm.py
```

---

### `claude_example.py` — Claude (Anthropic) Cost Tracking
**What it shows:** How to use Claude with the unified cost tracking system.

Requires: `ANTHROPIC_API_KEY` environment variable

```bash
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python examples/usage_tracking/claude_example.py
```

---

### `multi_step_agent.py` — Complex Workflow with Cost Aggregation
**What it shows:** Multi-step AI agent workflows with cumulative cost tracking.

Requires: `OPENAI_API_KEY` environment variable

```bash
$env:OPENAI_API_KEY = "sk-..."
python examples/usage_tracking/multi_step_agent.py
```

---

### `observability.py` — Cost Analytics & Event Inspection
**What it shows:** How to inspect, aggregate, and analyze cost events.

Features:
- Event history inspection
- Cost aggregation by model, provider, event type
- Estimated vs. actual token counts
- Event filtering and searching

Requires: `OPENAI_API_KEY` environment variable

```bash
$env:OPENAI_API_KEY = "sk-..."
python examples/usage_tracking/observability.py
```

---

### `missing_data.py` — Token Estimation Fallback
**What it shows:** How the cost tracking system handles missing token counts using estimation.

Features:
- Normalizer's automatic estimation when provider doesn't return tokens
- TokenEstimator fallback
- Estimated flag on events

Requires: `OPENAI_API_KEY` environment variable

```bash
$env:OPENAI_API_KEY = "sk-..."
python examples/usage_tracking/missing_data.py
```

---

## Architecture

All examples use the **unified cost tracking system**:

```
Adapter (OpenAI/Claude)
    ↓ executes LLM
    ↓ extracts usage
    ↓
Normalizer (converts to AIEvent)
    ↓
CostEngine (calculates cost)
    ↓
EventEmitter (publishes event)
    ↓
Your listeners/aggregators
```

### Key Components

- **CostEngine**: Calculates costs from AIEvent objects using PricingRegistry
- **EventEmitter**: Async pub/sub for cost events
- **PricingRegistry**: Time-bound pricing for all models
- **Normalizer**: Converts provider-specific responses to unified AIEvent format
- **AIEvent**: Universal event model with type, tokens, cost, metadata

## Supported Cost Types

| Type | Provider | Examples |
|------|----------|----------|
| **LLM_CALL** | OpenAI, Anthropic | gpt-4o, claude-3-sonnet |
| **EMBEDDING** | OpenAI | text-embedding-3-small/large |
| **IMAGE** | OpenAI | dall-e-2, dall-e-3 |
| **AUDIO** | OpenAI | whisper-1 |
| **TOOL_CALL** | All | Function execution overhead |
| **WEB_SEARCH** | Custom | Search API calls |

## Pricing (2026 Rates)

### OpenAI LLM
- gpt-4o: $2.50/M input, $10/M output
- gpt-4o-mini: $0.15/M input, $0.60/M output
- gpt-3.5-turbo: $0.50/M input, $1.50/M output

### Claude (Anthropic)
- Claude Haiku: $0.80/M input, $4/M output
- Claude Sonnet: $3/M input, $15/M output
- Claude Opus: $5/M input, $25/M output

### Embeddings & Images
- text-embedding-3-small: $0.02/M tokens
- text-embedding-3-large: $0.13/M tokens
- DALL-E 3: $0.04-0.12 per image (size dependent)

See `flint_ai/usage/pricing.py` for full pricing details.

## Environment Setup

### For OpenAI Examples
```powershell
$env:OPENAI_API_KEY = "sk-..."
```

### For Claude Examples
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

### For LangChain Integration
```powershell
pip install -e ".[langchain]"
```

## Common Patterns

### Pattern 1: Simple Cost Calculation
```python
from flint_ai.usage import CostEngine, PricingRegistry
from flint_ai.usage.events import AIEvent, EventType

pricing = PricingRegistry()
engine = CostEngine(pricing)

event = AIEvent(
    provider="openai",
    model="gpt-4o",
    type=EventType.LLM_CALL,
    input_tokens=1000,
    output_tokens=500,
)

cost = engine.calculate(event)
print(f"Cost: ${cost:.6f}")
```

### Pattern 2: Event-Driven Tracking
```python
from flint_ai.usage import EventEmitter

emitter = EventEmitter()

def on_event(event):
    print(f"Event: {event.type} cost=${event.cost_usd}")

emitter.subscribe(on_event)
emitter.emit(event)
```

### Pattern 3: Adapter Usage (with real LLM calls)
```python
from flint_ai.usage.adapters.openai import OpenAIAdapter
from flint_ai.usage import PricingRegistry, EventEmitter

pricing = PricingRegistry()
emitter = EventEmitter()

adapter = OpenAIAdapter(
    api_key="sk-...",
    pricing=pricing,
    emitter=emitter,
)

result = await adapter.execute_llm(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
    temperature=0.7,
    max_tokens=100,
)

print(f"Cost: ${result.cost_usd:.6f}")
```

## Next Steps

- **Add custom adapters**: Implement `BaseAdapter` for new LLM providers
- **Extend pricing**: Register custom models via `PricingRegistry.register()`
- **Build dashboards**: Use event history to visualize costs over time
- **Alert on budgets**: Subscribe to events and set cost thresholds
- **Export to analytics**: Send events to Datadog, Prometheus, or custom backends

---

For more details, see the main [README.md](../../README.md) and source code in `flint_ai/usage/`.
