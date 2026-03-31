"""
Flint Demo — Three AI Agents, One Pipeline
============================================

  pip install flint-ai[openai]
  docker compose -f docker-compose.dev.yml up -d
  set OPENAI_API_KEY=sk-...
  python demo.py
"""

import asyncio, json, time, uuid
from pydantic import BaseModel, Field
from flint_ai import Workflow, Node, AsyncOrchestratorClient
from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.adapters.core.worker import start_worker, stop_worker


# ── Pydantic models (optional — for structured output) ──────────────────

class ResearchData(BaseModel):
    topic: str
    findings: list[str]
    market_size: str = ""
    growth_rate: str = ""

class ReviewReport(BaseModel):
    score: float = Field(ge=0, le=10)
    verdict: str
    strengths: list[str]
    improvements: list[str]


# ── Agents — just config, no boilerplate classes ────────────────────────

researcher = FlintOpenAIAgent(
    name="researcher",
    model="gpt-4o-mini",
    instructions="Research the topic. Return 3-5 key findings with data points.",
    response_format={"type": "json_object"},
    temperature=0.3,
)

writer = FlintOpenAIAgent(
    name="writer",
    model="gpt-4o-mini",
    instructions="You receive research data from a previous agent. Write a polished executive summary (max 200 words).",
    temperature=0.5,
)

reviewer = FlintOpenAIAgent(
    name="reviewer",
    model="gpt-4o-mini",
    instructions="You receive an article from a previous agent. Review it for clarity and accuracy. Score out of 10.",
    response_format={"type": "json_object"},
    temperature=0.3,
)


# ── Pipeline — wire them up ─────────────────────────────────────────────

workflow = (
    Workflow(f"demo-{uuid.uuid4().hex[:6]}")
    .add(Node("research", agent=researcher, prompt="AI agent orchestration market in 2025"))
    .add(Node("write", agent=writer, prompt="Write executive summary from the research").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
)


# ── Run it ───────────────────────────────────────────────────────────────

async def main():
    print("🔥 Flint Demo — researcher → writer → reviewer (GPT-4o-mini)\n")

    await start_worker(port=5157)
    await asyncio.sleep(0.5)

    async with AsyncOrchestratorClient() as client:
        wf_id = await client.deploy_workflow(workflow)
        print(f"   Workflow: {wf_id}")
        print(f"   Dashboard: http://localhost:5156/dashboard/index.html\n")

        # Poll until all 3 agents finish
        agents = {"researcher": "research", "writer": "write", "reviewer": "review"}
        done = {}
        t0 = time.time()

        while len(done) < 3:
            resp = await client._request("GET", "/tasks", params={"workflowId": wf_id})
            for t in resp.json():
                name = t.get("agentType", "")
                state = t.get("state", "")
                if name in agents and name not in done:
                    if state == "Succeeded":
                        raw = t.get("result", "")
                        try:
                            output = json.loads(raw).get("Output", raw)
                        except Exception:
                            output = raw
                        done[name] = output
                        elapsed = time.time() - t0
                        preview = output[:150].replace("\n", " ")
                        print(f"  ✔ {agents[name]:10} ({name}) — {elapsed:.0f}s")
                        print(f"    {preview}...\n")
                    elif state in ("Failed", "DeadLetter"):
                        done[name] = f"FAILED: {t.get('result', '')[:100]}"
                        print(f"  ✘ {name} FAILED\n")
            await asyncio.sleep(2)

        print(f"✅ Done in {time.time() - t0:.0f}s\n")

        # Show structured outputs
        if "researcher" in done:
            try:
                data = ResearchData.model_validate_json(done["researcher"])
                print(f"📊 Research: {data.topic} — {len(data.findings)} findings, market: {data.market_size}")
            except Exception:
                pass

        if "reviewer" in done:
            try:
                review = ReviewReport.model_validate_json(done["reviewer"])
                print(f"⭐ Review: {review.score}/10 — {review.verdict}")
            except Exception:
                pass

    await stop_worker()

if __name__ == "__main__":
    asyncio.run(main())

