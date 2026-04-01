"""Demo: Flint + OpenAI — run real AI agents through the queue orchestrator.

This shows how to:
1. Register OpenAI agents with the embedded Flint engine
2. Submit tasks that get processed by GPT-4o-mini
3. Build a multi-step DAG workflow where each node is an AI agent call
4. View everything live in the dashboard UI

Prerequisites:
    pip install "flint-ai[server]" openai httpx
    export OPENAI_API_KEY="sk-..."   (or pass api_key= below)

Run:
    python examples/openai_demo.py

Then open:
    http://localhost:5160/ui/         (Dashboard)
    http://localhost:5160/ui/workflows (DAG Editor)
    http://localhost:5160/docs        (Swagger)
"""

import os
import sys
import time

import httpx

from flint_ai.adapters.openai import FlintOpenAIAgent
from flint_ai.adapters.openai.tools import tool
from flint_ai.server import FlintEngine, ServerConfig

# ---------------------------------------------------------------------------
# 1. Define tools the agents can use
# ---------------------------------------------------------------------------

@tool
def word_count(text: str) -> str:
    """Count the number of words in the given text."""
    count = len(text.split())
    return f"The text contains {count} words."


@tool
def summarize_list(items: str) -> str:
    """Take a comma-separated list and return a bullet-point summary."""
    parts = [x.strip() for x in items.split(",") if x.strip()]
    bullets = "\n".join(f"• {p}" for p in parts)
    return f"Summary ({len(parts)} items):\n{bullets}"


# ---------------------------------------------------------------------------
# 2. Create OpenAI-backed agents
# ---------------------------------------------------------------------------

# You can pass api_key= directly, or set OPENAI_API_KEY env var
api_key = os.environ.get("OPENAI_API_KEY", "")

# Agent 1: General-purpose analyst
analyst = FlintOpenAIAgent(
    name="analyst",
    model="gpt-4o-mini",
    instructions=(
        "You are a concise data analyst. When given a prompt, provide a short, "
        "structured analysis. Keep responses under 200 words."
    ),
    temperature=0.3,
    api_key=api_key,
)

# Agent 2: Writer with tools
writer = FlintOpenAIAgent(
    name="writer",
    model="gpt-4o-mini",
    instructions=(
        "You are a technical writer. You can use the word_count tool to check "
        "text length. Write clear, concise content."
    ),
    tools=[word_count],
    temperature=0.5,
    api_key=api_key,
)

# Agent 3: Summarizer
summarizer = FlintOpenAIAgent(
    name="summarizer",
    model="gpt-4o-mini",
    instructions=(
        "You are a summarization specialist. Condense the given content into "
        "3-5 bullet points. Be extremely concise."
    ),
    tools=[summarize_list],
    temperature=0.2,
    api_key=api_key,
)

# Agent 4: Reviewer / quality checker
reviewer = FlintOpenAIAgent(
    name="reviewer",
    model="gpt-4o-mini",
    instructions=(
        "You are a quality reviewer. Evaluate the given content for clarity, "
        "accuracy, and completeness. Provide a score (1-10) and brief feedback."
    ),
    temperature=0.3,
    api_key=api_key,
)


# ---------------------------------------------------------------------------
# 3. Create embedded engine and register agents
# ---------------------------------------------------------------------------

def main():
    if not api_key:
        print("=" * 60)
        print("  ⚠  OPENAI_API_KEY not set!")
        print()
        print("  Set it before running:")
        print("    export OPENAI_API_KEY='sk-...'")
        print("  Or on Windows:")
        print("    set OPENAI_API_KEY=sk-...")
        print("=" * 60)
        sys.exit(1)

    config = ServerConfig(port=5160, workers=4)
    engine = FlintEngine(config)

    # Register all 4 OpenAI agents
    engine.register_adapter(analyst)
    engine.register_adapter(writer)
    engine.register_adapter(summarizer)
    engine.register_adapter(reviewer)

    print("=" * 60)
    print("  Flint + OpenAI Demo")
    print("=" * 60)
    print()
    print("[ENGINE] Starting Flint with 4 OpenAI agents...")
    engine.start(blocking=False)
    print(f"[ENGINE] Running at {engine.url}")
    print(f"[ENGINE] UI:      {engine.url}/ui/")
    print(f"[ENGINE] Swagger:  {engine.url}/docs")
    print()

    client = httpx.Client(base_url=engine.url, timeout=60)

    # Verify health
    r = client.get("/health")
    print(f"[CHECK] Health: {r.json()}")

    # List registered agents
    agents = client.get("/agents").json()
    print(f"[CHECK] Agents: {[a['agent_type'] for a in agents]}")
    print()

    # -------------------------------------------------------------------
    # 4. Submit individual tasks
    # -------------------------------------------------------------------
    print("─" * 60)
    print("  Phase 1: Individual Tasks")
    print("─" * 60)

    tasks = [
        {
            "agent_type": "analyst",
            "prompt": "Analyze the key trends in AI agent orchestration for 2025. "
                      "Cover: multi-agent collaboration, DAG workflows, and human-in-the-loop patterns.",
        },
        {
            "agent_type": "writer",
            "prompt": "Write a short paragraph (under 100 words) explaining what a "
                      "dead-letter queue is and why it matters in production AI systems.",
        },
        {
            "agent_type": "summarizer",
            "prompt": "Summarize the benefits of using a DAG-based workflow engine for AI agents: "
                      "parallel execution, dependency management, conditional branching, "
                      "retry policies, human approval gates, fan-out/fan-in patterns.",
        },
    ]

    task_ids = []
    for t in tasks:
        r = client.post("/tasks", json=t)
        tid = r.json()["id"]
        task_ids.append(tid)
        print(f"  Submitted: {t['agent_type']:12s} → {tid[:12]}...")

    # Wait for tasks to complete
    print("\n  Waiting for AI responses", end="", flush=True)
    for _ in range(60):
        time.sleep(1)
        print(".", end="", flush=True)
        all_done = True
        for tid in task_ids:
            state = client.get(f"/tasks/{tid}").json()["state"]
            if state not in ("succeeded", "failed", "dead_letter"):
                all_done = False
                break
        if all_done:
            break
    print()

    # Show results
    print()
    for tid in task_ids:
        t = client.get(f"/tasks/{tid}").json()
        print(f"  [{t['state'].upper():10s}] {t['agent_type']}")
        if t["state"] == "succeeded" and t.get("result_json"):
            # Show first 200 chars of result
            preview = t["result_json"][:200]
            print(f"    → {preview}{'...' if len(t['result_json']) > 200 else ''}")
        elif t.get("error"):
            print(f"    ✗ Error: {t['error'][:150]}")
        print()

    # -------------------------------------------------------------------
    # 5. Create and run a multi-step workflow
    # -------------------------------------------------------------------
    print("─" * 60)
    print("  Phase 2: DAG Workflow — Content Pipeline")
    print("─" * 60)
    print()
    print("  Workflow: research → [review-gate 🔒] → [draft, outline] → final-review")
    print("  (review-gate requires human approval before draft+outline proceed)")
    print()

    workflow = {
        "id": "content-pipeline",
        "name": "AI Content Pipeline",
        "nodes": [
            {
                "id": "research",
                "agent_type": "analyst",
                "prompt_template": (
                    "Research the topic: 'How queue orchestration improves AI agent reliability'. "
                    "Provide 5 key findings with supporting reasoning."
                ),
            },
            {
                "id": "review-gate",
                "agent_type": "reviewer",
                "prompt_template": (
                    "Review the research findings below and decide if they are strong enough "
                    "to base a blog post on. Score clarity 1-10 and list any gaps."
                ),
                "human_approval": True,
            },
            {
                "id": "draft",
                "agent_type": "writer",
                "prompt_template": (
                    "Based on the research and review, write a 150-word blog post section about "
                    "queue orchestration for AI agents. Focus on reliability and fault tolerance."
                ),
            },
            {
                "id": "outline",
                "agent_type": "summarizer",
                "prompt_template": (
                    "Create a bullet-point outline for an article about AI agent orchestration. "
                    "Include sections on: architecture, retry strategies, DAG workflows, monitoring."
                ),
            },
            {
                "id": "final-review",
                "agent_type": "reviewer",
                "prompt_template": (
                    "Review the following content plan for a technical blog about AI queue orchestration. "
                    "Score it 1-10 on clarity, depth, and actionability. Suggest improvements."
                ),
            },
        ],
        "edges": [
            {"from_node_id": "research", "to_node_id": "review-gate"},
            {"from_node_id": "review-gate", "to_node_id": "draft"},
            {"from_node_id": "review-gate", "to_node_id": "outline"},
            {"from_node_id": "draft", "to_node_id": "final-review"},
            {"from_node_id": "outline", "to_node_id": "final-review"},
        ],
    }

    # Create the workflow
    r = client.post("/workflows", json=workflow)
    print(f"  Created workflow: {r.json()['id']}")

    # Start the run
    r = client.post("/workflows/content-pipeline/start", json={})
    run_id = r.json()["id"]
    print(f"  Started run:      {run_id[:12]}...")
    print()

    # Monitor the run
    print("  DAG Progression:")
    last_states = {}
    approval_handled = False
    for tick in range(120):
        time.sleep(2)
        r = client.get(f"/workflows/runs/{run_id}")
        run = r.json()
        node_states = run.get("node_states", {})

        # Print new state changes
        for node, state in node_states.items():
            if node not in last_states or last_states[node] != state:
                symbol = {
                    "queued": "⏳", "running": "🔄", "succeeded": "✅",
                    "failed": "❌", "pending": "🔒", "dead_letter": "💀",
                }.get(state, "?")
                print(f"    {symbol} {node:14s} → {state}")
                last_states[node] = state

        # Handle human approval gate
        if (
            not approval_handled
            and node_states.get("review-gate") == "pending"
            and node_states.get("research") == "succeeded"
        ):
            print()
            print("  ┌────────────────────────────────────────────────┐")
            print("  │  🔒 HUMAN APPROVAL REQUIRED: review-gate      │")
            print("  │                                                │")
            # Show the research result that will feed into the review
            research_tasks = run.get("task_ids", {}).get("research")
            if research_tasks:
                task_id = research_tasks if isinstance(research_tasks, str) else research_tasks[0] if research_tasks else None
                if task_id:
                    t = client.get(f"/tasks/{task_id}").json()
                    preview = (t.get("result_json") or "")[:120]
                    print(f"  │  Research output: {preview[:46]}│")
            print("  │                                                │")
            print("  │  Auto-approving in 3 seconds...                │")
            print("  │  (In production, use the UI or API to approve) │")
            print("  └────────────────────────────────────────────────┘")
            time.sleep(3)

            # Approve the node via API
            approve_r = client.post(f"/workflows/runs/{run_id}/nodes/review-gate/approve")
            print(f"\n    ✅ review-gate  → approved (task: {approve_r.json().get('task_id', '?')[:12]}...)")
            approval_handled = True

        if run["state"] in ("succeeded", "failed"):
            print(f"\n  Workflow run: {run['state'].upper()}")
            break
    else:
        print("\n  (timed out waiting — check UI for status)")

    # -------------------------------------------------------------------
    # 6. Show node-to-node data passing (enriched prompts)
    # -------------------------------------------------------------------
    print()
    print("─" * 60)
    print("  Phase 3: Node-to-Node Data Passing (XCom)")
    print("─" * 60)
    print()
    print("  Showing how upstream results flow into downstream prompts:")

    # Get all workflow tasks
    r = client.get(f"/workflows/runs/{run_id}")
    run_data = r.json()
    for node_id in ["research", "review-gate", "draft", "outline", "final-review"]:
        task_id = run_data.get("task_ids", {}).get(node_id)
        if task_id:
            t = client.get(f"/tasks/{task_id}").json()
            print(f"\n  📌 {node_id}")

            # Show if prompt was enriched (contains [Output from ...])
            prompt_preview = t["prompt"]
            if "[Output from" in prompt_preview:
                # Extract upstream references
                import re
                refs = re.findall(r"\[Output from (\w[\w-]*)\]", prompt_preview)
                print(f"     ← Received data from: {', '.join(refs)}")
                # Show first 100 chars of the enriched part
                print(f"     Prompt starts: {prompt_preview[:100]}...")
            else:
                print(f"     (root node — no upstream data)")

            if t.get("result_json"):
                result_preview = t["result_json"][:100]
                print(f"     Result: {result_preview}{'...' if len(t['result_json']) > 100 else ''}")

    # -------------------------------------------------------------------
    # 7. Show final dashboard
    # -------------------------------------------------------------------
    print()
    print("─" * 60)
    print("  Dashboard Summary")
    print("─" * 60)
    s = client.get("/dashboard/summary").json()
    print(f"  Total tasks:   {s['total']}")
    for state, count in s.get("by_state", {}).items():
        print(f"    {state:15s}: {count}")
    print(f"  Queue depth:   {s['queue_length']}")
    print(f"  Dead letters:  {s['dlq_length']}")
    print(f"  Workers:       {s['worker_count']}")

    print()
    print("=" * 60)
    print(f"  🎯 Open the UI to see everything:")
    print(f"     Dashboard:  {engine.url}/ui/")
    print(f"     Workflows:  {engine.url}/ui/workflows")
    print(f"     Runs:       {engine.url}/ui/runs")
    print(f"     Tasks:      {engine.url}/ui/tasks")
    print(f"     Swagger:    {engine.url}/docs")
    print(f"")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)

    # Keep alive for UI browsing
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[ENGINE] Shutting down...")
        engine.stop()
        print("[ENGINE] Done.")


if __name__ == "__main__":
    main()
