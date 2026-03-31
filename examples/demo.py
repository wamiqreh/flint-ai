"""
Flint Demo — Structured Pipeline with Pydantic Models
=======================================================

Three GPT-4o-mini agents pass structured Pydantic objects through a DAG:

  [Researcher] → [Writer] → [Reviewer]
       ↓              ↓           ↓
  ResearchData    Article    ReviewReport

Each agent receives the previous agent's structured JSON output
and parses it into a Pydantic model before processing.

Usage:
  set OPENAI_API_KEY=sk-...
  docker compose -f docker-compose.dev.yml up -d
  pip install flint-ai[openai]
  python demo.py
"""

import asyncio
import json
import time
import uuid
from typing import Optional
from pydantic import BaseModel, Field

from flint_ai import Workflow, Node, AsyncOrchestratorClient
from flint_ai.adapters.core.base import FlintAdapter
from flint_ai.adapters.core.types import AgentRunResult, ErrorMapping
from flint_ai.adapters.core.worker import start_worker, stop_worker


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Models — structured data flowing between agents
# ═══════════════════════════════════════════════════════════════════════════

class Finding(BaseModel):
    title: str
    detail: str
    confidence: float = Field(ge=0, le=1, description="0-1 confidence score")


class ResearchData(BaseModel):
    """Output of the Researcher agent."""
    topic: str
    findings: list[Finding]
    market_size_usd: Optional[str] = None
    growth_rate: Optional[str] = None


class Article(BaseModel):
    """Output of the Writer agent."""
    title: str
    summary: str
    sections: list[str]
    word_count: int
    based_on_findings: int = Field(description="Number of research findings used")


class ReviewReport(BaseModel):
    """Output of the Reviewer agent."""
    score: float = Field(ge=0, le=10)
    verdict: str
    strengths: list[str]
    improvements: list[str]
    article_title: str


# ═══════════════════════════════════════════════════════════════════════════
# Agents — each returns a structured Pydantic model as JSON
# ═══════════════════════════════════════════════════════════════════════════

class ResearcherAgent(FlintAdapter):
    """Calls GPT-4o-mini, returns structured ResearchData."""

    def __init__(self):
        super().__init__(
            name="researcher",
            error_mapping=ErrorMapping(retry_on=[TimeoutError, ConnectionError]),
        )

    async def run(self, input_data: dict) -> AgentRunResult:
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a research analyst. Return ONLY valid JSON matching this schema:\n"
                    + ResearchData.model_json_schema().__repr__() + "\n"
                    "Include 3-5 findings with confidence scores. Be factual and concise."
                )},
                {"role": "user", "content": input_data["prompt"]},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        raw = response.choices[0].message.content
        # Validate it parses as our Pydantic model
        data = ResearchData.model_validate_json(raw)
        print(f"  📊 Researcher → {len(data.findings)} findings, market: {data.market_size_usd}")

        return AgentRunResult(
            output=data.model_dump_json(indent=2),
            metadata={"findings_count": len(data.findings), "model": "gpt-4o-mini"},
        )


class WriterAgent(FlintAdapter):
    """Receives ResearchData JSON, calls GPT, returns structured Article."""

    def __init__(self):
        super().__init__(
            name="writer",
            error_mapping=ErrorMapping(retry_on=[TimeoutError, ConnectionError]),
        )

    async def run(self, input_data: dict) -> AgentRunResult:
        from openai import AsyncOpenAI

        prompt = input_data["prompt"]

        # Parse upstream research data from the prompt
        # The engine prepends: [Output from 'research']:\n{json}\n\n---\n\nWrite summary
        research = None
        if "[Output from 'research']:" in prompt:
            json_part = prompt.split("[Output from 'research']:")[1].split("---")[0].strip()
            try:
                research = ResearchData.model_validate_json(json_part)
                print(f"  📥 Writer received {len(research.findings)} structured findings from Researcher")
            except Exception:
                pass

        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are a technical writer. You receive research data and write an article.\n"
                    "Return ONLY valid JSON matching this schema:\n"
                    + Article.model_json_schema().__repr__() + "\n"
                    "Use the research findings to write a compelling summary."
                )},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
        )

        raw = response.choices[0].message.content
        article = Article.model_validate_json(raw)
        print(f"  📝 Writer → \"{article.title}\" ({article.word_count} words, {article.based_on_findings} findings used)")

        return AgentRunResult(
            output=article.model_dump_json(indent=2),
            metadata={"word_count": article.word_count, "model": "gpt-4o-mini"},
        )


class ReviewerAgent(FlintAdapter):
    """Receives Article JSON, calls GPT, returns structured ReviewReport."""

    def __init__(self):
        super().__init__(
            name="reviewer",
            error_mapping=ErrorMapping(retry_on=[TimeoutError, ConnectionError]),
        )

    async def run(self, input_data: dict) -> AgentRunResult:
        from openai import AsyncOpenAI

        prompt = input_data["prompt"]

        # Parse upstream article
        article = None
        if "[Output from 'write']:" in prompt:
            json_part = prompt.split("[Output from 'write']:")[1].split("---")[0].strip()
            try:
                article = Article.model_validate_json(json_part)
                print(f"  📥 Reviewer received article: \"{article.title}\"")
            except Exception:
                pass

        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You are an editor reviewing an article. Return ONLY valid JSON matching this schema:\n"
                    + ReviewReport.model_json_schema().__repr__() + "\n"
                    "Give an honest score 0-10, list strengths and improvements."
                )},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        raw = response.choices[0].message.content
        review = ReviewReport.model_validate_json(raw)
        print(f"  ⭐ Reviewer → {review.score}/10 — {review.verdict}")

        return AgentRunResult(
            output=review.model_dump_json(indent=2),
            metadata={"score": review.score, "verdict": review.verdict, "model": "gpt-4o-mini"},
        )


# ═══════════════════════════════════════════════════════════════════════════
# Main — build DAG, deploy, watch results
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print("=" * 64)
    print("  Flint — Structured Pydantic Pipeline (Real GPT-4o-mini)")
    print("=" * 64)
    print()
    print("  Models:  ResearchData → Article → ReviewReport")
    print("  Agents:  [researcher] → [writer] → [reviewer]")
    print()

    # Start inline worker
    print("🔧 Starting inline worker...")
    await start_worker(port=5157)
    await asyncio.sleep(0.5)

    # Build workflow
    wf_id = f"structured-pipeline-{uuid.uuid4().hex[:6]}"
    workflow = (
        Workflow(wf_id)
        .add(Node("research", agent=ResearcherAgent(),
                   prompt="Research the AI agent orchestration market in 2025. "
                          "Cover market size, top 3 players, and key trends."))
        .add(Node("write", agent=WriterAgent(),
                   prompt="Write an executive summary article from the research data.")
             .depends_on("research"))
        .add(Node("review", agent=ReviewerAgent(),
                   prompt="Review this article for quality, accuracy, and completeness.")
             .depends_on("write"))
    )

    # Deploy
    print("🚀 Deploying to Flint...\n")
    async with AsyncOrchestratorClient(base_url="http://localhost:5156") as client:
        workflow_id = await client.deploy_workflow(workflow)
        print(f"   Workflow: {workflow_id}")
        print(f"   Dashboard: http://localhost:5156/dashboard/index.html\n")
        print("─" * 64)

        # Poll for results
        agent_to_node = {"researcher": "research", "writer": "write", "reviewer": "review"}
        completed = {}
        results = {}
        start_time = time.time()

        while len(completed) < 3:
            resp = await client._request("GET", "/tasks", params={"workflowId": workflow_id})
            tasks = resp.json()

            for t in tasks:
                agent = t.get("agentType", "")
                state = t.get("state", "")
                if agent in agent_to_node and agent not in completed:
                    if state == "Succeeded":
                        elapsed = time.time() - start_time
                        completed[agent] = elapsed

                        # Parse result
                        result_raw = t.get("result", "")
                        try:
                            parsed = json.loads(result_raw)
                            output = parsed.get("Output", result_raw)
                        except (ValueError, TypeError):
                            output = result_raw
                        results[agent] = output

                    elif state in ("Failed", "DeadLetter"):
                        completed[agent] = -1
                        error = t.get("result", t.get("error", "unknown"))
                        print(f"\n  ✘ {agent} FAILED: {error[:200]}")

            if len(completed) < 3:
                await asyncio.sleep(2)

        # Print structured results
        elapsed = time.time() - start_time
        print()
        print("=" * 64)
        print(f"  ✅ Pipeline completed in {elapsed:.1f}s")
        print("=" * 64)

        # Show each agent's Pydantic output
        if "researcher" in results:
            print("\n📊 ResearchData (Pydantic):")
            print("─" * 40)
            try:
                data = ResearchData.model_validate_json(results["researcher"])
                print(f"  Topic: {data.topic}")
                print(f"  Market: {data.market_size_usd}  Growth: {data.growth_rate}")
                for f in data.findings:
                    print(f"  • [{f.confidence:.0%}] {f.title}: {f.detail[:80]}")
            except Exception:
                print(f"  {results['researcher'][:300]}")

        if "writer" in results:
            print("\n📝 Article (Pydantic):")
            print("─" * 40)
            try:
                article = Article.model_validate_json(results["writer"])
                print(f"  Title: {article.title}")
                print(f"  Words: {article.word_count}  Findings used: {article.based_on_findings}")
                print(f"  Summary: {article.summary[:200]}...")
                print(f"  Sections: {', '.join(article.sections)}")
            except Exception:
                print(f"  {results['writer'][:300]}")

        if "reviewer" in results:
            print("\n⭐ ReviewReport (Pydantic):")
            print("─" * 40)
            try:
                review = ReviewReport.model_validate_json(results["reviewer"])
                print(f"  Score: {review.score}/10 — {review.verdict}")
                print(f"  Article: \"{review.article_title}\"")
                print(f"  Strengths: {', '.join(review.strengths)}")
                print(f"  Improvements: {', '.join(review.improvements)}")
            except Exception:
                print(f"  {results['reviewer'][:300]}")

    await stop_worker()
    print(f"\n🛑 Done!")


if __name__ == "__main__":
    asyncio.run(main())
