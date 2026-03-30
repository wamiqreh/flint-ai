etailed Development Plan: Building Official Adapters for Popular Agent SDKs*

*Project:* Flint-AI  
*Feature:* Adapters (Phase 1 – OpenAI + Core Foundation)  
*Target:* v0.3.0  
*Owner:* Dev Team  
*Timeline:* 4–6 weeks (start today, March 29, 2026)  
*Goal:* Make Flint the easiest production layer for any existing OpenAI SDK agent while keeping full DAG power.

This is the *exact plan* you (or the devs) can follow right now.

### 1. Overall Architecture (Final Desired State)

mermaid
graph TD
    DeveloperCode[Your OpenAI SDK Agent] --> Adapter[FlintOpenAIAgent / FlintLangGraph etc.]
    Adapter --> AutoRegister[Automatic Registration]
    AutoRegister --> InlineWorker[Inline Worker - runs inside Flint]
    InlineWorker --> RedisQueue[Redis Queue + DAG Engine]
    DAGEngine --> VisualEditor[Visual Editor + Dashboard]
    DAGEngine --> DLQ[Dead Letter Queue]


### 2. New Folder Structure to Create

Create these folders/files inside the repo:


sdks/python/flint_ai/
├── adapters/                          ← NEW (main folder)
│   ├── __init__.py
│   ├── core/                          ← NEW
│   │   ├── __init__.py
│   │   ├── base.py                    ← FlintAdapter abstract class
│   │   ├── registry.py                ← Auto-registration logic
│   │   ├── worker.py                  ← Inline FastAPI/Starlette worker
│   │   └── types.py                   ← Shared models (RegisteredAgent, etc.)
│   ├── openai/                        ← Phase 1 (highest priority)
│   │   ├── __init__.py
│   │   ├── agent.py                   ← FlintOpenAIAgent class
│   │   └── tools.py                   ← Tool decorator + helpers
│   ├── langgraph/                     ← Phase 2
│   └── crewai/                        ← Phase 3
├── __init__.py                        ← Add: from .adapters import FlintOpenAIAgent
└── orchestrator.py                    ← Update to support adapter objects


Also update:
- sdks/python/pyproject.toml (add extras)
- templates/python-starter/ (new adapter examples)
- examples/adapters/ (new folder with demos)
- README.md + docs/adapters.md

### 3. Step-by-Step Implementation Plan

*Week 1: Core Adapter Foundation + OpenAI Adapter (MVP)*

*Day 1–2: Core Layer*
1. Create adapters/core/base.py
   - class FlintAdapter(ABC) with abstract methods:
     - async def run(self, input_data: dict) -> dict
     - def get_agent_name(self) -> str
     - def to_registered_agent(self) -> dict
2. Create adapters/core/registry.py
   - Auto-register function that calls internal /agents/register or uses Flint’s in-memory registry for inline mode.
3. Create adapters/core/worker.py
   - Lightweight FastAPI app that runs inside the Flint worker process.
   - Handles /execute internally for inline agents.

*Day 3–5: OpenAI Adapter*
Create adapters/openai/agent.py with this *exact public API*:

python
from flint_ai.adapters.openai import FlintOpenAIAgent
from openai import OpenAI
from flint_ai import tool

@tool
def analyze_diff(diff: str) -> str: ...

agent = FlintOpenAIAgent(
    name="pr_reviewer",           # required
    model="gpt-4o",
    instructions="You are an expert...",
    tools=[analyze_diff],
    temperature=0.1,
    streaming=False
)

# Automatic registration happens on __init__ or first run


*Key Requirements for OpenAI Adapter:*
- Support full openai.chat.completions.create
- Support OpenAI Agents SDK (tools + handoffs)
- Support streaming
- Pass through API key from env or explicit
- Handle errors → map to Flint retry/DLQ

*Week 2: DAG Integration + Testing*

1. Update flint_ai/Workflow and Node classes so you can do:
   python
   wf.add_node(Node(id="review", agent=reviewer))   # ← pass object, not string
   
2. Update OrchestratorClient to accept adapter objects and convert them internally.
3. Add integration tests (mock OpenAI + real Flint instance).

*Week 3: Polish & Examples*
- CLI: flint init openai-pr-reviewer
- Full example in examples/adapters/openai-pr-reviewer
- Update README with new “Adapters” section (use the vision text I gave earlier)
- Side-by-side comparison table

*Week 4–6: Next Adapters + DLQ Hero Feature*
- LangGraph Adapter
- CrewAI Adapter
- Build the beautiful DLQ dashboard (this is the differentiator)

### 4. Technical Details You Must Follow

- Use *inline mode* by default (run inside Flint worker) → zero extra HTTP.
- Keep *webhook mode* as fallback for backward compatibility.
- All adapters must implement the same FlintAdapter interface.
- Use pyproject.toml extras: flint-ai[openai], flint-ai[langgraph]
- Add proper typing, docstrings, and error messages.
- OpenTelemetry tracing must pass through automatically.

### 5. Testing Requirements
- Unit tests for every adapter class
- Integration test: create agent → build workflow → run → check result
- Test with real OpenAI key (use pytest-vcr or mocks)
- Test failure path → must land in DLQ correctly

### 6. Deliverables Checklist (PR Ready)

- [x] Core adapter layer complete (base.py, registry.py, worker.py, types.py)
- [x] FlintOpenAIAgent working with natural OpenAI-style code
- [x] Can pass adapter object directly to Node(agent=...)
- [x] `client.deploy_workflow()` auto-registers adapters + creates + starts
- [x] `@tool` decorator with OpenAI-compatible schema generation
- [x] Error mapping: rate limits → retry, bad requests → fail, unknown → DLQ
- [x] Inline worker (runs in-process, no extra HTTP hop)
- [x] `pip install flint-ai[openai]` extras in pyproject.toml
- [x] PR Reviewer example (examples/adapters/openai-pr-reviewer/)
- [x] Updated README with native adapter section
- [x] All existing webhook agents still work unchanged
- [x] CrewAI adapter
- [x] Editor UI: dynamic agent dropdown, webhook/crewai support
- [x] Enhanced DLQ dashboard (filtering, bulk restart, detail modal)
- [x] 54 passing tests (unit + integration with mocked OpenAI)
- [x] OpenTelemetry tracing in base adapter
- [ ] LangGraph adapter
- [ ] Streaming support (SSE task output)
- [ ] Hosted tier (managed Flint)

---

This plan directly supports the long-term vision: *Flint becomes the OS for production AI agents*