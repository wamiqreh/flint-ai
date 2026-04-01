"""Quickstart — run a 3-node AI workflow in ~20 lines.

    pip install "flint-ai[server]" openai
    export OPENAI_API_KEY="sk-..."
    python examples/quickstart.py
"""

from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(
    name="researcher", model="gpt-4o-mini",
    instructions="Research the topic. Return key findings.",
    response_format={"type": "json_object"},
)
writer = FlintOpenAIAgent(
    name="writer", model="gpt-4o-mini",
    instructions="Write a polished summary from the research.",
)
reviewer = FlintOpenAIAgent(
    name="reviewer", model="gpt-4o-mini",
    instructions="Review the article. Score out of 10.",
    response_format={"type": "json_object"},
)

results = (
    Workflow("demo")
    .add(Node("research", agent=researcher, prompt="AI orchestration 2025"))
    .add(Node("write", agent=writer, prompt="Summarize the research").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
    .run()
)

print("\n📊 Research:", results["research"][:200])
print("\n📝 Article:", results["write"][:200])
print("\n⭐ Review:", results["review"][:200])
