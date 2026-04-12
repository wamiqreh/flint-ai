# Flint AI Examples

Complete working examples for all Flint AI features.

## 🚀 Start Here: Quickstart (NEW!)

**New to Flint?** Start with the [quickstart/](quickstart/) folder — minimal, self-contained examples (15-25 lines each):

- **[01_hello_workflow.py](quickstart/01_hello_workflow.py)** — 3-node sequential pipeline (no API key)
- **[02_with_cost_tracking.py](quickstart/02_with_cost_tracking.py)** — Same + automatic cost tracking (OpenAI key)
- **[03_embedded_worker.py](quickstart/03_embedded_worker.py)** — Embedded mode with custom worker settings
- **[04_approval_gates.py](quickstart/04_approval_gates.py)** — Human approval in workflow
- **[05_parallel_branches.py](quickstart/05_parallel_branches.py)** — Fan-out / fan-in pattern

See [quickstart/README.md](quickstart/README.md) for full details.

---

## Basics
- **[embedded_demo.py](basics/embedded_demo.py)** — Flint in-process server (like Hangfire) with task queue and workflows
- **[workflow_builder.py](basics/workflow_builder.py)** — Building DAGs with the Workflow/Node DSL
- **[demo.py](basics/demo.py)** — Three-step workflow (research → write → review) *requires OpenAI key*
- **[parallel_branches.py](basics/parallel_branches.py)** — Parallel execution in DAG workflows
- **[human_approval.py](basics/human_approval.py)** — Adding approval gates to workflows

### 💰 Cost Tracking (NEW!)
**See [usage_tracking/README.md](usage_tracking/README.md) for all cost tracking examples**

- **[embedding_image_costs.py](usage_tracking/embedding_image_costs.py)** ⭐ — Multimodal cost calculation (embeddings, images, vision)
- **[simple_llm.py](usage_tracking/simple_llm.py)** — Basic LLM cost tracking *requires OpenAI key*
- **[claude_example.py](usage_tracking/claude_example.py)** — Claude (Anthropic) with unified cost system *requires Anthropic key*
- **[multi_step_agent.py](usage_tracking/multi_step_agent.py)** — Complex workflows with cumulative costs *requires OpenAI key*
- **[observability.py](usage_tracking/observability.py)** — Cost analytics and event inspection *requires OpenAI key*
- **[missing_data.py](usage_tracking/missing_data.py)** — Token estimation fallback *requires OpenAI key*

### 📊 Advanced Scenarios
- **[full_demo.py](advanced/full_demo.py)** — Comprehensive demo: cost tracking + tool logging + workflows + UI *requires OpenAI key*
- **[prod_demo.py](advanced/prod_demo.py)** — Production patterns: retries, error handling, concurrency limits
- **[production_scenarios.py](advanced/production_scenarios.py)** — Real-world use cases: multi-agent teams, fan-out/fan-in
- **[real_ai_workflow.py](advanced/real_ai_workflow.py)** — Complete AI agent orchestration pipeline

### 🔗 Provider Integration
- **[openai_workflow.py](openai/openai_workflow.py)** — OpenAI with Flint Workflow DSL
- **[openai_demo.py](openai/openai_demo.py)** — Standalone OpenAI agent
- **[openai_server_mode.py](openai/openai_server_mode.py)** — Running Flint server separately

## Feature Matrix

| Feature | Basic Examples | Cost Tracking | Advanced |
|---------|---|---|---|
| **Embedded mode** | ✅ `embedded_demo.py` | — | — |
| **Workflow DAG** | ✅ `workflow_builder.py`, `demo.py` | — | ✅ `real_ai_workflow.py` |
| **Parallel execution** | ✅ `parallel_branches.py` | — | ✅ `production_scenarios.py` |
| **Approval gates** | ✅ `human_approval.py` | — | — |
| **Cost calculation** | — | ✅ `embedding_image_costs.py` | ✅ `full_demo.py` |
| **Embeddings** | — | ✅ `embedding_image_costs.py` | — |
| **Image generation** | — | ✅ `embedding_image_costs.py` | — |
| **Vision analysis** | — | ✅ `embedding_image_costs.py` | — |
| **Claude adapter** | — | ✅ `claude_example.py` | — |
| **OpenAI adapter** | ✅ `openai_*.py` | ✅ `simple_llm.py` | ✅ `full_demo.py` |
| **Error handling** | — | — | ✅ `prod_demo.py` |
| **Concurrency limits** | — | — | ✅ `prod_demo.py` |
| **Multi-agent teams** | — | — | ✅ `production_scenarios.py` |

## Running Examples

### No API Key Needed
```bash
python examples/basics/embedded_demo.py
python examples/usage_tracking/embedding_image_costs.py  # ⭐ NEW
```

### With OpenAI Key
```bash
$env:OPENAI_API_KEY = "sk-..."
python examples/basics/demo.py
python examples/advanced/full_demo.py
python examples/usage_tracking/simple_llm.py
```

### With Anthropic Key
```bash
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python examples/usage_tracking/claude_example.py
```

## Installation

```bash
# Basic: core + embedded server + both OpenAI and Anthropic
pip install -e ".[all]"

# Or install specific extras:
pip install -e "."           # core only
pip install -e ".[openai]"   # with OpenAI
pip install -e ".[server]"   # with server (for separate process)
```

## Learning Path

**Beginner:**
1. Start with `basics/embedded_demo.py` — see Flint in action
2. Run `usage_tracking/embedding_image_costs.py` — understand cost tracking
3. Build a simple workflow with `basics/workflow_builder.py`

**Intermediate:**
4. Explore `basics/demo.py` with your OpenAI key
5. Try `usage_tracking/multi_step_agent.py` to see workflow + costs together
6. Study `advanced/production_scenarios.py` for real-world patterns

**Advanced:**
7. Build multi-agent teams with `production_scenarios.py`
8. Integrate with your framework (LangChain, CrewAI, etc.)
9. Deploy with Redis + Postgres for persistence (see README.md)

## Key Concepts

### Embedded Mode (Hangfire-like)
Flint can run as an in-process server in your Python app:
```python
engine = FlintEngine(ServerConfig(port=5157))
engine.start(blocking=False)  # background thread
# Now use Flint like a task queue
```

### Workflow DAG
Define complex multi-step AI orchestrations:
```python
workflow = (Workflow("my-pipeline")
    .add(Node("step1", agent=agent1))
    .add(Node("step2", agent=agent2).depends_on("step1"))
    .add(Node("step3", agent=agent3).depends_on("step2"))
    .build())

results = workflow.run()
```

### Unified Cost Tracking ⭐
Cost tracking is **enabled by default** — no manual tracker needed:
```python
from flint_ai.adapters.openai import FlintOpenAIAgent

agent = FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini")
# Cost is auto-tracked from centralized CostConfigManager (DB or defaults)
```

Customize:
```python
# Disable cost tracking
agent = FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini", enable_cost_tracking=False)

# Override pricing for this agent
agent = FlintOpenAIAgent(name="summarizer", model="gpt-4o-mini",
                         cost_config_override={"prompt": 5.0, "completion": 20.0})
```

Centralized pricing management:
```python
from flint_ai.config import CostConfigManager, get_pricing, set_pricing

# Get current pricing
pricing = get_pricing("gpt-4o")

# Runtime override (in-memory only, not persisted)
set_pricing("gpt-4o", {"prompt": 5.0, "completion": 20.0})
```

### Adapters
Flint provides two adapter patterns:

1. **Workflow adapters** (FlintOpenAIAgent, FlintAnthropicAgent):
   - For use in Workflow/Node DSL
   - Use old cost_tracker system
   - Example: `basic/demo.py`

2. **Unified adapters** (OpenAIAdapter, AnthropicAdapter):
   - For new cost tracking system
   - Event-driven, provider-agnostic
   - Example: `usage_tracking/simple_llm.py`

Both coexist — choose based on your needs.

## Dashboard

When running embedded mode or with a server, explore:
- **Dashboard**: `http://localhost:5160/ui/`
- **Costs**: `http://localhost:5160/ui/costs`
- **Tools**: `http://localhost:5160/ui/tools`
- **Runs**: `http://localhost:5160/ui/runs`
- **Swagger**: `http://localhost:5160/docs`

## Troubleshooting

**"anthropic library required"**
```bash
pip install anthropic
```

**"openai library required"**
```bash
pip install openai
```

**API key errors**
```bash
# Check key is set
$env:OPENAI_API_KEY
$env:ANTHROPIC_API_KEY

# PowerShell
$env:OPENAI_API_KEY = "sk-..."
```

**Port in use (e.g., 5157)**
```python
config = ServerConfig(port=5158)  # use different port
engine = FlintEngine(config)
```

## Contributing

Have a great example? Submit a PR! We'd love to add it.

## See Also

- Main [README.md](../README.md)
- [Cost Tracking Guide](usage_tracking/README.md)
- [Architecture Docs](../docs/)
- [API Reference](../docs/api/)
