"""OpenAI multi-agent workflow with data passing between nodes.

Usage:
    OPENAI_API_KEY=sk-... python examples/openai_workflow.py

Three GPT agents collaborate in a pipeline:
  research → write → review

Each node automatically receives the output from its upstream dependencies.
"""

from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(
    name="researcher",
    model="gpt-4o-mini",
    instructions="Research the topic. Return 3-5 key findings with supporting data.",
    response_format={"type": "json_object"},
)
writer = FlintOpenAIAgent(
    name="writer",
    model="gpt-4o-mini",
    instructions="Write a polished executive summary from the research (max 200 words).",
)
reviewer = FlintOpenAIAgent(
    name="reviewer",
    model="gpt-4o-mini",
    instructions="Review the article for clarity, accuracy, and completeness. Score out of 10.",
    response_format={"type": "json_object"},
)

results = (
    Workflow("research-pipeline")
    .add(Node("research", agent=researcher, prompt="AI agent orchestration market in 2025"))
    .add(Node("write", agent=writer, prompt="Write executive summary").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
    .run()
)

print("\n📊 Research:", results["research"][:300])
print("\n📝 Article:", results["write"][:300])
print("\n⭐ Review:", results["review"][:300])
