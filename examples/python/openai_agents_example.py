"""
Flint + OpenAI Agents SDK Integration Example
=============================================

This shows how to use the OpenAI Agents SDK (https://github.com/openai/openai-agents-python)
with Flint's webhook agent. Your OpenAI agent runs as a FastAPI service,
and Flint orchestrates it (retries, DAG workflows, human-in-the-loop).

Setup:
  pip install openai-agents fastapi uvicorn flint-ai

Architecture:
  ┌─────────────┐     webhook      ┌──────────────────────┐
  │  Flint API   │ ──── POST ────▶ │  Your Agent Service   │
  │ (orchestrator)│ ◀── response ── │  (OpenAI Agents SDK)  │
  └─────────────┘                  └──────────────────────┘

  Flint handles: queue, retries, DAG, approval, DLQ
  Your service handles: the actual AI agent logic
"""

from fastapi import FastAPI, Request
from agents import Agent, Runner, function_tool
import uvicorn

app = FastAPI()

# ── Define your OpenAI agent with tools ──────────────────────────

@function_tool
def get_weather(city: str) -> str:
    """Get the weather for a city."""
    # In production, call a real weather API
    return f"The weather in {city} is 72°F and sunny."

@function_tool
def search_database(query: str) -> str:
    """Search the internal database."""
    return f"Found 3 results for '{query}'"

# Create an OpenAI agent with tools and instructions
research_agent = Agent(
    name="research-assistant",
    instructions="""You are a research assistant. Use your tools to gather
    information and provide comprehensive answers. Always cite your sources.""",
    tools=[get_weather, search_database],
    model="gpt-4o-mini",
)

code_review_agent = Agent(
    name="code-reviewer",
    instructions="""You are a senior code reviewer. Analyze the code provided
    and give actionable feedback on bugs, security issues, and improvements.""",
    model="gpt-4o",
)

# ── Webhook endpoint that Flint calls ────────────────────────────

@app.post("/agents/research")
async def run_research(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    task_id = body.get("task_id", "")

    # Run the OpenAI agent — supports multi-turn, tool calls, etc.
    result = await Runner.run(research_agent, prompt)

    return {
        "task_id": task_id,
        "output": result.final_output,
        "success": True,
    }

@app.post("/agents/code-review")
async def run_code_review(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    task_id = body.get("task_id", "")

    result = await Runner.run(code_review_agent, prompt)

    return {
        "task_id": task_id,
        "output": result.final_output,
        "success": True,
    }


# ── Multi-agent handoff example ──────────────────────────────────

triage_agent = Agent(
    name="triage",
    instructions="Route the request to the right specialist.",
    handoffs=[research_agent, code_review_agent],
    model="gpt-4o-mini",
)

@app.post("/agents/triage")
async def run_triage(request: Request):
    body = await request.json()
    result = await Runner.run(triage_agent, body.get("prompt", ""))
    return {"output": result.final_output, "success": True}


# ── Register with Flint and create a workflow ────────────────────

async def register_with_flint():
    """Call this on startup to register agents with Flint."""
    from flint_ai import AsyncOrchestratorClient, WorkflowBuilder

    client = AsyncOrchestratorClient("http://localhost:5156")

    # Option 1: Set WEBHOOK_AGENT_URL env var and use agentType: "webhook"
    # Option 2: Register custom agent types dynamically:
    import httpx
    await httpx.AsyncClient().post("http://localhost:5156/agents/register", json={
        "name": "research",
        "url": "http://localhost:8000/agents/research"
    })
    await httpx.AsyncClient().post("http://localhost:5156/agents/register", json={
        "name": "code-review",
        "url": "http://localhost:8000/agents/code-review"
    })

    # Create a workflow: research → human review → code review
    wf = (WorkflowBuilder("ai-pipeline")
        .add_node("research", agent_type="research", prompt="Research the topic: {input}")
        .add_node("review", agent_type="dummy", prompt="Review research", human_approval=True)
        .add_node("code-review", agent_type="code-review", prompt="Review the implementation")
        .add_edge("research", "review")
        .add_edge("review", "code-review")
        .build())

    await client.create_workflow(wf)
    print("✅ Agents registered and workflow created!")


if __name__ == "__main__":
    print("🚀 Starting OpenAI Agents service on http://localhost:8000")
    print("   POST /agents/research   — Research assistant with tools")
    print("   POST /agents/code-review — Code reviewer")
    print("   POST /agents/triage      — Multi-agent router")
    print()
    print("Register with Flint: python -c 'import asyncio; from openai_agents_example import register_with_flint; asyncio.run(register_with_flint())'")
    uvicorn.run(app, host="0.0.0.0", port=8000)
