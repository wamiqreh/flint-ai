"""
OpenAI Three-Agent Pipeline — Real LLM Demo
=============================================

  [Researcher] → [Writer] → [Reviewer]

Each agent is a real FlintOpenAIAgent calling GPT-4o.
The Flint orchestrator manages the DAG — each agent waits
for the previous one to finish before starting.

Requirements:
  - Flint API running:  docker compose -f docker-compose.dev.yml up -d
  - pip install flint-ai[openai] uvicorn starlette httpx

Usage:
  set OPENAI_API_KEY=sk-...
  python main.py
"""

import asyncio
import json
import time
from flint_ai import Workflow, Node, AsyncOrchestratorClient
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.adapters.core.worker import start_worker, stop_worker


# ── Three real OpenAI agents ────────────────────────────────────────────────

researcher = FlintOpenAIAgent(
    name="researcher",
    model="gpt-4o-mini",
    instructions=(
        "You are a research analyst. Given a topic, provide 3-5 key findings "
        "with data points. Be concise — max 150 words."
    ),
)

writer = FlintOpenAIAgent(
    name="writer",
    model="gpt-4o-mini",
    instructions=(
        "You are a technical writer. Take research findings and write a short, "
        "polished executive summary (max 200 words). Use clear headings."
    ),
)

reviewer = FlintOpenAIAgent(
    name="reviewer",
    model="gpt-4o-mini",
    instructions=(
        "You are an editor. Review the text for clarity, accuracy, and tone. "
        "Give a quality score out of 10 and list 2-3 specific improvements. "
        "End with APPROVED or NEEDS REVISION."
    ),
)


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Flint — OpenAI Three-Agent Pipeline (Real LLM)")
    print("=" * 60)
    print("\n📋 DAG: [researcher/gpt-4o-mini] → [writer/gpt-4o-mini] → [reviewer/gpt-4o-mini]\n")

    # 1) Start inline worker
    print("🔧 Starting inline worker on port 5157...")
    await start_worker(port=5157)
    await asyncio.sleep(0.5)

    # 2) Build workflow
    import uuid
    wf_id = f"openai-pipeline-{uuid.uuid4().hex[:6]}"

    workflow = (
        Workflow(wf_id)
        .add(Node("research", agent=researcher,
                   prompt="Research the current state of AI agent orchestration frameworks in 2025. "
                          "Cover market size, top players, and key trends."))
        .add(Node("write", agent=writer,
                   prompt="Write an executive summary from the research findings above.")
             .depends_on("research"))
        .add(Node("review", agent=reviewer,
                   prompt="Review this executive summary for quality and accuracy.")
             .depends_on("write"))
    )

    # 3) Deploy
    print("🚀 Deploying workflow to Flint...\n")
    async with AsyncOrchestratorClient(base_url="http://localhost:5156") as client:
        workflow_id = await client.deploy_workflow(workflow)
        print(f"   Workflow: {workflow_id}")
        print(f"   Dashboard: http://localhost:5156/dashboard/index.html\n")

        # 4) Poll and display results as they complete
        agent_to_node = {"researcher": "research", "writer": "write", "reviewer": "review"}
        node_order = ["researcher", "writer", "reviewer"]
        completed = {}
        start_time = time.time()

        print("⏳ Waiting for agents (real GPT-4o-mini calls)...\n")

        while len(completed) < 3:
            resp = await client._request("GET", "/tasks", params={"workflowId": workflow_id})
            tasks = resp.json()

            for t in tasks:
                agent = t.get("agentType", "")
                state = t.get("state", "")
                if agent in agent_to_node and agent not in completed:
                    if state == "Succeeded":
                        elapsed = time.time() - start_time
                        node = agent_to_node[agent]

                        # Parse the result
                        result_raw = t.get("result", "")
                        try:
                            parsed = json.loads(result_raw)
                            output = parsed.get("Output", result_raw)
                        except (ValueError, TypeError):
                            output = result_raw

                        completed[agent] = output
                        print(f"  ✔ {node} ({agent}) — {elapsed:.1f}s")
                        print(f"  {'─' * 50}")
                        # Show first 300 chars of output
                        preview = output[:300] + ("..." if len(output) > 300 else "")
                        for line in preview.split("\n"):
                            print(f"    {line}")
                        print()

                    elif state in ("Failed", "DeadLetter"):
                        completed[agent] = f"FAILED: {t.get('error', 'unknown')}"
                        print(f"  ✘ {agent_to_node[agent]} ({agent}) FAILED")
                        print(f"    {t.get('result', t.get('error', 'unknown'))}\n")

            if len(completed) < 3:
                await asyncio.sleep(2)

        # 5) Summary
        elapsed = time.time() - start_time
        print(f"{'=' * 60}")
        print(f"  ✅ Pipeline completed in {elapsed:.1f}s")
        print(f"{'=' * 60}")

    await stop_worker()
    print("\n🛑 Done!")


if __name__ == "__main__":
    asyncio.run(main())
