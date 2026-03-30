"""OpenAI PR Reviewer — Flint adapter example.

This example shows how to use the FlintOpenAIAgent adapter to build
a code review pipeline that runs entirely through Flint's orchestration.

Usage:
    pip install flint-ai[openai]
    export OPENAI_API_KEY=sk-...
    python main.py

What happens:
    1. Three agents are created using natural OpenAI-style code
    2. Tools are defined with the @tool decorator
    3. A DAG workflow wires them together: generate → review → summarize
    4. One call to deploy_workflow() registers agents, creates the workflow, and starts it
"""

from flint_ai import OrchestratorClient, Workflow, Node, tool
from flint_ai.adapters.openai import FlintOpenAIAgent


# ── Tools ──────────────────────────────────────────────────────────────────

@tool
def analyze_diff(diff: str) -> str:
    """Analyze a code diff and return structured findings."""
    # In production, this would parse real git diffs
    return f"Analysis of diff ({len(diff)} chars): No critical issues found. Style: good. Tests: needed."


@tool
def check_security(code: str) -> str:
    """Check code for common security vulnerabilities."""
    issues = []
    if "eval(" in code:
        issues.append("⚠️ eval() usage detected — potential code injection")
    if "password" in code.lower() and "hash" not in code.lower():
        issues.append("⚠️ Plaintext password detected")
    if not issues:
        return "✅ No security issues found"
    return "\n".join(issues)


@tool
def count_lines(code: str) -> str:
    """Count lines of code."""
    lines = code.strip().split("\n")
    return f"Total lines: {len(lines)}, Non-empty: {sum(1 for l in lines if l.strip())}"


# ── Agents ─────────────────────────────────────────────────────────────────

code_generator = FlintOpenAIAgent(
    name="code_generator",
    model="gpt-4o-mini",
    instructions="""You are an expert Python developer.
    Generate clean, well-documented code based on the user's request.
    Always include type hints and docstrings.""",
    temperature=0.3,
)

code_reviewer = FlintOpenAIAgent(
    name="code_reviewer",
    model="gpt-4o",
    instructions="""You are a senior code reviewer. Analyze the code for:
    - Correctness and edge cases
    - Performance issues
    - Security vulnerabilities (use the check_security tool)
    - Code style and readability
    Give a score from 1-10 and specific suggestions.""",
    tools=[analyze_diff, check_security, count_lines],
    temperature=0.1,
)

summarizer = FlintOpenAIAgent(
    name="summarizer",
    model="gpt-4o-mini",
    instructions="""Summarize the code review into a brief executive summary.
    Include: overall score, top 3 findings, and a go/no-go recommendation.""",
    temperature=0.2,
)


# ── Workflow ───────────────────────────────────────────────────────────────

def main():
    client = OrchestratorClient("http://localhost:5156")

    # Build workflow with adapter objects — not string agent names
    wf = (Workflow("pr-review-pipeline")
        .add(Node("generate", agent=code_generator,
                   prompt="Write a Python REST API with user authentication using FastAPI"))
        .add(Node("review", agent=code_reviewer,
                   prompt="Review this code thoroughly")
             .depends_on("generate")
             .requires_approval()      # Human must approve before review starts
             .with_retries(2))
        .add(Node("summarize", agent=summarizer,
                   prompt="Summarize the review findings")
             .depends_on("review"))
    )

    # One call: registers agents → creates workflow → starts execution
    workflow_id = client.deploy_workflow(wf)
    print(f"🔥 Workflow started: {workflow_id}")
    print(f"📊 Dashboard: http://localhost:5156/dashboard/index.html")
    print(f"🎨 Editor: http://localhost:5156/editor/index.html")


if __name__ == "__main__":
    main()
