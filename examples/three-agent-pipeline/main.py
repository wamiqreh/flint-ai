"""
Three-Agent Pipeline — Flint Sample Project
=============================================

Demonstrates a DAG workflow where three agents run in sequence:

  [Researcher] → [Writer] → [Reviewer]

Each agent is a lightweight FlintAdapter subclass (no LLM API key needed).
The Flint orchestrator manages the queue, retries, and DAG dependencies.

Requirements:
  - Flint API running at http://localhost:5156
  - pip install flint-ai uvicorn starlette httpx

Usage:
  python main.py
"""

import asyncio
import time
from flint_ai import Workflow, Node, AsyncOrchestratorClient
from flint_ai.adapters.core.base import FlintAdapter
from flint_ai.adapters.core.types import AgentRunResult, ErrorMapping
from flint_ai.adapters.core.worker import start_worker, stop_worker

# ── Agent 1: Researcher ─────────────────────────────────────────────────────

class ResearcherAgent(FlintAdapter):
    """Simulates research by extracting key topics from the prompt."""

    def __init__(self):
        super().__init__(
            name="researcher",
            error_mapping=ErrorMapping(retry_on=[TimeoutError]),
        )

    async def run(self, input_data: dict) -> AgentRunResult:
        prompt = input_data.get("prompt", "")
        # Simulate research work
        await asyncio.sleep(1)
        research = (
            f"Research findings on '{prompt}':\n"
            f"1. Key insight: The topic has 3 major dimensions\n"
            f"2. Market data: Growing at 25% YoY\n"
            f"3. Expert consensus: High potential for disruption\n"
            f"4. Risk factors: Regulatory uncertainty, competition"
        )
        print(f"  ✅ Researcher completed — found 4 insights")
        return AgentRunResult(output=research, metadata={"insights_count": 4})


# ── Agent 2: Writer ──────────────────────────────────────────────────────────

class WriterAgent(FlintAdapter):
    """Takes research output and writes a structured summary."""

    def __init__(self):
        super().__init__(
            name="writer",
            error_mapping=ErrorMapping(retry_on=[TimeoutError]),
        )

    async def run(self, input_data: dict) -> AgentRunResult:
        prompt = input_data.get("prompt", "")
        await asyncio.sleep(1)
        article = (
            f"# Executive Summary\n\n"
            f"Based on our research analysis:\n\n"
            f"{prompt}\n\n"
            f"## Conclusion\n"
            f"The evidence suggests significant opportunity with manageable risks. "
            f"Recommended action: proceed with phased investment strategy."
        )
        word_count = len(article.split())
        print(f"  ✅ Writer completed — {word_count} words")
        return AgentRunResult(output=article, metadata={"word_count": word_count})


# ── Agent 3: Reviewer ────────────────────────────────────────────────────────

class ReviewerAgent(FlintAdapter):
    """Reviews the written article and provides quality score + feedback."""

    def __init__(self):
        super().__init__(
            name="reviewer",
            error_mapping=ErrorMapping(retry_on=[TimeoutError]),
        )

    async def run(self, input_data: dict) -> AgentRunResult:
        prompt = input_data.get("prompt", "")
        await asyncio.sleep(1)
        review = (
            f"## Review Report\n\n"
            f"**Quality Score: 8.5/10**\n\n"
            f"### Strengths\n"
            f"- Well-structured with clear sections\n"
            f"- Data-driven conclusions\n"
            f"- Actionable recommendations\n\n"
            f"### Suggestions\n"
            f"- Add specific competitor analysis\n"
            f"- Include timeline estimates\n\n"
            f"**Verdict: APPROVED for publication**"
        )
        print(f"  ✅ Reviewer completed — score 8.5/10")
        return AgentRunResult(
            output=review,
            metadata={"quality_score": 8.5, "verdict": "approved"},
        )


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Flint — Three-Agent Pipeline Demo")
    print("=" * 60)

    # 1) Create adapter instances
    researcher = ResearcherAgent()
    writer = WriterAgent()
    reviewer = ReviewerAgent()

    # 2) Build the workflow DAG: researcher → writer → reviewer
    import uuid
    wf_id = f"research-pipeline-{uuid.uuid4().hex[:6]}"
    workflow = (
        Workflow(wf_id)
        .add(Node("research", agent=researcher, prompt="Analyze the AI agent orchestration market"))
        .add(Node("write", agent=writer, prompt="Write executive summary from research").depends_on("research"))
        .add(Node("review", agent=reviewer, prompt="Review the article for quality").depends_on("write"))
    )

    print("\n📋 Workflow DAG:")
    print("   [researcher] → [writer] → [reviewer]\n")

    # 3) Start the inline worker (HTTP server on port 5157)
    print("🔧 Starting inline worker on port 5157...")
    worker = await start_worker(port=5157)
    await asyncio.sleep(0.5)  # let server start

    # 4) Deploy and run the workflow
    print("🚀 Deploying workflow to Flint...\n")
    async with AsyncOrchestratorClient(base_url="http://localhost:5156") as client:
        workflow_id = await client.deploy_workflow(workflow)
        print(f"   Workflow ID: {workflow_id}")
        print(f"   Dashboard:   http://localhost:5156/dashboard/index.html\n")

        # 5) Poll for completion — watch tasks finish in DAG order
        #    The /tasks?workflowId= endpoint returns tasks with agentType.
        #    Map agent names back to node IDs for display.
        agent_to_node = {"researcher": "research", "writer": "write", "reviewer": "review"}
        print("⏳ Watching pipeline execute...\n")
        start_time = time.time()
        completed_agents = set()
        expected_agents = {"researcher", "writer", "reviewer"}

        while completed_agents != expected_agents:
            resp = await client._request("GET", "/tasks", params={"workflowId": workflow_id})
            tasks = resp.json()
            for t in tasks:
                agent = t.get("agentType", "")
                state = t.get("state", "")
                if agent in expected_agents and agent not in completed_agents:
                    if state == "Succeeded":
                        completed_agents.add(agent)
                        node_id = agent_to_node.get(agent, agent)
                        elapsed = time.time() - start_time
                        print(f"  ✔ Node '{node_id}' ({agent}) succeeded [{elapsed:.1f}s]")
                    elif state in ("Failed", "DeadLetter"):
                        completed_agents.add(agent)
                        node_id = agent_to_node.get(agent, agent)
                        print(f"  ✘ Node '{node_id}' ({agent}) failed: {t.get('error', 'unknown')}")

            if completed_agents != expected_agents:
                await asyncio.sleep(1)

        # 6) Print final results
        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"  ✅ Pipeline completed in {elapsed:.1f}s")
        print(f"{'=' * 60}")

        # Fetch and display the final reviewer output
        resp = await client._request("GET", "/tasks", params={"workflowId": workflow_id})
        tasks = resp.json()
        for t in tasks:
            if t.get("agentType") == "reviewer" and t.get("state") == "Succeeded":
                import json as _json
                result = t.get("result", "")
                try:
                    parsed = _json.loads(result)
                    output = parsed.get("Output", result)
                except (ValueError, TypeError):
                    output = result
                print(f"\n📝 Final Review Output:\n{'-' * 40}")
                print(output)
                break

    # 7) Cleanup
    await stop_worker()
    print("\n🛑 Worker stopped. Done!")


if __name__ == "__main__":
    asyncio.run(main())
