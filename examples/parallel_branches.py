"""Parallel branch workflow — fan-out and fan-in.

Usage:
    OPENAI_API_KEY=sk-... python examples/parallel_branches.py

DAG shape:
    research ──┬── draft_blog
               ├── draft_tweet
               └── draft_email ──→ final_review
"""

from flint_ai import Workflow, Node
from flint_ai.adapters.openai import FlintOpenAIAgent

researcher = FlintOpenAIAgent(
    name="researcher", model="gpt-4o-mini",
    instructions="Research the topic and return key findings.",
)
blog_writer = FlintOpenAIAgent(
    name="blog_writer", model="gpt-4o-mini",
    instructions="Write a short blog post from the research (150 words max).",
)
tweet_writer = FlintOpenAIAgent(
    name="tweet_writer", model="gpt-4o-mini",
    instructions="Write a compelling tweet thread (3 tweets) from the research.",
)
email_writer = FlintOpenAIAgent(
    name="email_writer", model="gpt-4o-mini",
    instructions="Write a newsletter email from the research (100 words max).",
)
reviewer = FlintOpenAIAgent(
    name="reviewer", model="gpt-4o-mini",
    instructions="Review all content pieces for consistency and quality. Score each out of 10.",
    response_format={"type": "json_object"},
)

results = (
    Workflow("content-pipeline")
    .add(Node("research", agent=researcher, prompt="AI agents in production — trends for 2025"))
    .add(Node("blog", agent=blog_writer, prompt="Write blog post").depends_on("research"))
    .add(Node("tweet", agent=tweet_writer, prompt="Write tweet thread").depends_on("research"))
    .add(Node("email", agent=email_writer, prompt="Write newsletter").depends_on("research"))
    .add(Node("review", agent=reviewer, prompt="Review all content").depends_on("blog", "tweet", "email"))
    .run()
)

for name, output in results.items():
    print(f"\n{'━'*50}\n🔹 {name}:\n{output[:250]}")
