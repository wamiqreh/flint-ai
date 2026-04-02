"""OpenAI workflow — SERVER MODE (client-worker architecture).

This example connects to a RUNNING Flint server and submits the workflow.
Agents execute locally on YOUR machine (with your API keys), while the
server handles orchestration, DAG execution, retries, and the dashboard.

Step 1: Start the server (in another terminal):
    python -m flint_ai.server --port 5156

Step 2: Run this example:
    OPENAI_API_KEY=sk-... python examples/openai_server_mode.py

Step 3: Open the dashboard:
    http://localhost:5156/ui/

Key difference from openai_workflow.py:
  - openai_workflow.py runs everything in-process (embedded mode)
  - This file talks to a remote server, but agents still run here on YOUR machine
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

# server_url connects to Flint server — agents execute locally via FlintWorker
results = (
    Workflow("research-pipeline")
    .add(Node("research", agent=researcher, prompt="AI agent orchestration market in 2025"))
    .add(Node("write", agent=writer, prompt="Write executive summary").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
    .run(server_url="http://localhost:5156")
)

print("\n📊 Research:", results["research"][:300])
print("\n📝 Article:", results["write"][:300])
print("\n⭐ Review:", results["review"][:300])
