# OpenAI + Anthropic Integration Guide

This guide explains how Flint AI now focuses exclusively on **OpenAI** and **Anthropic** (Claude) support with two complementary systems.

## Two Adapter Systems (By Design)

Flint provides **two different adapter patterns** to serve different use cases:

### System 1: Workflow Adapters (FlintOpenAIAgent, FlintAnthropicAgent)

**For:** Workflow/Node DSL, DAG orchestration, approval gates

**Location:** `flint_ai/adapters/openai/` and `flint_ai/adapters/anthropic/`

**Cost System:** Old `FlintCostTracker` (tightly coupled)

**Use when:**
- Building workflows with `Workflow().add(Node())`
- You need tool calling and approval gates
- You want simple, integrated cost tracking

**Example:**
```python
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai import Workflow, Node

agent = FlintOpenAIAgent(
    name="researcher",
    model="gpt-4o",
    instructions="Research the topic",
)

workflow = (Workflow("my-pipeline")
    .add(Node("research", agent=agent, prompt="AI in 2025"))
    .build())

results = workflow.run()
```

---

### System 2: Unified Adapters (OpenAIAdapter, AnthropicAdapter)

**For:** Event-driven cost tracking, provider-agnostic architecture

**Location:** `flint_ai/usage/adapters/`

**Cost System:** New `CostEngine` + `EventEmitter` (decoupled, modern)

**Use when:**
- You need detailed cost analytics
- You want event-driven architecture
- You need provider-agnostic design
- You track multiple modalities (embeddings, images, audio)

**Example:**
```python
from flint_ai.usage.adapters.openai import OpenAIAdapter
from flint_ai.usage import CostEngine, EventEmitter, PricingRegistry

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

---

## Supported Models

### OpenAI

| Model | Use Case | Cost |
|-------|----------|------|
| gpt-4o | Latest, best quality | $2.50/M input, $10/M output |
| gpt-4o-mini | Faster, cheaper | $0.15/M input, $0.60/M output |
| gpt-3.5-turbo | Legacy | $0.50/M input, $1.50/M output |
| text-embedding-3-small | Embeddings | $0.02/M tokens |
| text-embedding-3-large | Embeddings (better) | $0.13/M tokens |
| dall-e-3 | Image generation | $0.04-0.12 per image |
| dall-e-2 | Image generation (legacy) | $0.016-0.020 per image |

### Anthropic (Claude)

| Model | Use Case | Cost |
|-------|----------|------|
| claude-3-5-sonnet-20241022 | Latest, best | $3/M input, $15/M output |
| claude-3-5-haiku-20241022 | Fast, cheap | $0.80/M input, $4/M output |
| claude-3-opus-20250219 | Most capable | $5/M input, $25/M output |

---

## Quick Start by Use Case

### 1. Simple LLM Call (No Workflow)

```bash
# Embedded mode
python examples/usage_tracking/simple_llm.py

# Cost tracking for OpenAI
$env:OPENAI_API_KEY = "sk-..."
python examples/usage_tracking/simple_llm.py

# Cost tracking for Claude
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python examples/usage_tracking/claude_example.py
```

### 2. Workflow with Multiple Agents

```bash
# Uses FlintOpenAIAgent (or replace with FlintAnthropicAgent)
$env:OPENAI_API_KEY = "sk-..."
python examples/basics/demo.py
```

### 3. Multimodal Cost Tracking

```bash
# Track embeddings, images, vision - no API key needed!
python examples/usage_tracking/embedding_image_costs.py
```

### 4. Embedded Server (Like Global engine)

```bash
# In-process server in background thread
python examples/basics/embedded_mode_guide.py

# Open dashboard: http://localhost:5160/ui/
```

### 5. Separate Server Process

```bash
# Terminal 1 - Start server
python -m flint_ai.server.run --port 5160 \
  --queue redis://localhost:6379 \
  --store postgres://localhost/flint_db \
  --workers 4

# Terminal 2+ - Use from your app
python examples/basics/server_mode_guide.py
```

---

## Deployment Modes

### Embedded Mode (Development/Testing)

**Pros:**
- Zero setup
- Server + app in one process (like Global engine)
- Perfect for development

**Cons:**
- Python only
- Single machine only
- State lost on restart (use Redis+Postgres for persistence)

**Code:**
```python
from flint_ai.server import FlintEngine, ServerConfig

config = ServerConfig(port=5160)
engine = FlintEngine(config)
engine.start(blocking=False)  # Runs in background

# Your app keeps running normally
# Access at http://localhost:5160/ui/
```

### Server Mode (Production)

**Pros:**
- Separate process
- Multi-language clients (HTTP API)
- Horizontal scaling
- Persistent state (Redis + Postgres)

**Cons:**
- More complex setup
- Network overhead

**Command:**
```bash
python -m flint_ai.server.run --port 5160 \
  --queue redis://localhost:6379 \
  --store postgres://localhost/flint_db \
  --workers 4
```

**Decision Matrix:**

| Need | Embedded | Server |
|------|----------|--------|
| Development | ✅ | — |
| Production | ⚠️ | ✅ |
| Persistence | ⚠️ (optional) | ✅ (required) |
| Scale | ❌ | ✅ |
| Simple | ✅ | — |

---

## Cost Tracking Architecture

### What's Supported

✅ **LLM Calls** — Input + output tokens

✅ **Embeddings** — text-embedding-3-small/large

✅ **Images** — DALL-E 2/3

✅ **Vision** — GPT-4 with images

✅ **Audio** — Whisper (seconds)

✅ **Caching** — Claude cache read tokens

✅ **Tools** — Function calling overhead

### Example: Track All Modalities

```bash
python examples/usage_tracking/embedding_image_costs.py
```

**Output:**
```
[OK] Embeddings (2 calls):        $0.000750
[OK] Image generation (1 call):   $0.120000
[OK] Vision analysis (1 call):    $0.010000
------
Total multimodal cost:            $0.130750
```

---

## Tool Calling

Both adapters support tool calling:

### With FlintOpenAIAgent (Workflow)

```python
from flint_ai import tool

@tool
def search_code(query: str) -> str:
    """Search codebase for code."""
    return f"Found results for {query}"

agent = FlintOpenAIAgent(
    name="code-reviewer",
    model="gpt-4o",
    tools=[search_code],
)

# Use in workflow
result = agent.run(
    prompt="Review this PR",
    context={},
)
```

### With AnthropicAdapter (Unified)

```python
from flint_ai.usage.adapters.anthropic import AnthropicAdapter

adapter = AnthropicAdapter(api_key="sk-ant-...")

# Tool calling happens automatically
result = await adapter.execute_llm(
    model="claude-3-5-sonnet-20241022",
    messages=[...],
    tools=[
        {
            "name": "search_code",
            "description": "Search codebase",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    ],
)
```

---

## Environment Setup

### OpenAI

```powershell
# PowerShell
$env:OPENAI_API_KEY = "sk-..."

# Or add to profile
echo '$env:OPENAI_API_KEY = "sk-..."' >> $PROFILE
```

### Anthropic

```powershell
# PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Or add to profile
echo '$env:ANTHROPIC_API_KEY = "sk-ant-..."' >> $PROFILE
```

---

## What Changed (Cleanup)

✅ **Removed:**
- CrewAI adapter (`flint_ai/adapters/crewai/`)
- LangChain adapter examples
- Unnecessary framework integrations

✅ **Kept:**
- OpenAI (FlintOpenAIAgent + OpenAIAdapter)
- Anthropic (FlintAnthropicAgent + AnthropicAdapter)
- All core Flint functionality

✅ **Result:**
- Focused, maintainable codebase
- Two proven adapter patterns
- Clear examples for both systems

---

## Examples Available

### Basics (No API Key)
- `examples/basics/embedded_demo.py` — Global engine-like embedded mode
- `examples/basics/embedded_mode_guide.py` — Detailed embedded example
- `examples/basics/server_mode_guide.py` — Server mode setup
- `examples/basics/workflow_builder.py` — DAG building
- `examples/basics/parallel_branches.py` — Parallel execution
- `examples/basics/human_approval.py` — Approval gates

### Cost Tracking (Some require API key)
- `examples/usage_tracking/embedding_image_costs.py` ⭐ — **No API key!**
- `examples/usage_tracking/simple_llm.py` — OpenAI cost tracking
- `examples/usage_tracking/claude_example.py` — Claude cost tracking
- `examples/usage_tracking/multi_step_agent.py` — Complex workflows
- `examples/usage_tracking/observability.py` — Cost analytics
- `examples/usage_tracking/missing_data.py` — Token estimation

### Advanced
- `examples/advanced/full_demo.py` — Everything: workflows + costs + UI
- `examples/advanced/prod_demo.py` — Production patterns
- `examples/advanced/production_scenarios.py` — Real-world examples
- `examples/advanced/real_ai_workflow.py` — Complex orchestration

### Provider Integration
- `examples/openai/openai_workflow.py` — OpenAI + Workflow DSL
- `examples/openai/openai_demo.py` — Standalone OpenAI
- `examples/openai/openai_server_mode.py` — Server setup

---

## Test Coverage

✅ 279 tests pass
✅ 0 lint errors
✅ 0 formatting errors
✅ Full test coverage for:
  - FlintOpenAIAgent
  - FlintAnthropicAgent
  - OpenAIAdapter
  - AnthropicAdapter
  - CostEngine
  - PricingRegistry
  - EventEmitter
  - Multimodal costs

---

## Next Steps

1. **Choose your adapter:**
   - Workflow? → Use `FlintOpenAIAgent` or `FlintAnthropicAgent`
   - Event-driven? → Use `OpenAIAdapter` or `AnthropicAdapter`

2. **Choose your deployment:**
   - Development? → Embedded mode
   - Production? → Server mode + Redis + Postgres

3. **Explore examples:**
   ```bash
   python examples/usage_tracking/embedding_image_costs.py
   python examples/basics/embedded_demo.py
   python examples/basics/demo.py  # Requires OpenAI key
   ```

4. **See the guides:**
   - `examples/README.md` — All examples overview
   - `examples/DEPLOYMENT_GUIDE.md` — Embedded vs Server comparison
   - `examples/usage_tracking/README.md` — Cost tracking deep dive

---

**Questions?** Check the examples first — they cover most use cases!

