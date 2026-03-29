# Content Marketing — Flint

## Content Calendar

| # | Title | Status | Target Publish | Platform |
|---|-------|--------|---------------|----------|
| 1 | Why Your AI Agents Need a Queue (And What Happens When They Don't) | 📝 Draft | Week 1 | dev.to, Hashnode, company blog |
| 2 | From LangChain Prototype to Production: Adding Reliability to AI Workflows | 📝 Draft | Week 3 | dev.to, Hashnode, company blog |
| 3 | Building an AI Code Review Pipeline with DAG Workflows | 📝 Draft | Week 5 | dev.to, Hashnode, company blog |

### Publishing cadence
- **Every two weeks** — gives time for promotion and audience engagement between posts.
- Posts build on each other (series format) but each stands alone.

### Planned future posts
| # | Title | Topic |
|---|-------|-------|
| 4 | Real-Time Agent Monitoring: SSE vs WebSocket for Task Streaming | Observability |
| 5 | Scaling AI Agents on Kubernetes with Helm and HPA | Infrastructure |
| 6 | The Agent Adapter Pattern: Supporting OpenAI, Claude, and Custom LLMs | Architecture |
| 7 | Dead Letter Queues for AI: Why Your Failed Tasks Deserve a Second Chance | Reliability |

---

## Style Guide

### Tone
- **Technical but accessible** — assume the reader writes code daily but may not know queue theory or distributed systems patterns.
- **Practical over theoretical** — every concept should have a code example or architecture diagram.
- **Honest, not salesy** — discuss trade-offs, acknowledge when simpler solutions exist. The product mentions should feel natural, not forced.
- **Conversational** — write like you're explaining to a colleague, not presenting at a conference.

### Structure
Every post should follow this pattern:
1. **Hook** (1–2 paragraphs) — A relatable pain point or scenario.
2. **Problem** — What goes wrong and why. Be specific with error messages, failure modes, and real numbers.
3. **Solution** — The pattern or concept that fixes it. Explain the "why" before the "how."
4. **Code** — Working examples with comments. Before/after comparisons are highly effective.
5. **Call to action** — Link to the next post in the series or the quickstart guide. Keep it brief.

### Formatting
- Use ATX-style headers (`#`, `##`, `###`).
- Code blocks with language hints (```python, ```bash, ```json).
- ASCII architecture diagrams for visual learners (renders everywhere, no image hosting needed).
- Tables for comparisons and feature lists.
- Front matter (YAML) for title, description, tags, date — compatible with most static site generators and blogging platforms.

### Word count
- Target **800–1000 words** per post.
- Code examples don't count toward word count but should be concise and runnable.

### Voice and language
- Use "you" and "your" — speak directly to the reader.
- Avoid jargon without explanation. First use of a term like "DLQ" should spell it out: "dead letter queue (DLQ)."
- No exclamation marks in technical explanations. Save them for genuinely exciting results.
- Prefer active voice: "The worker picks up the task" over "The task is picked up by the worker."

---

## Target Audience

### Primary: Backend developers using LLM APIs
- Building features with OpenAI, Anthropic, or similar APIs.
- Running into production issues (rate limits, failures, no observability).
- Familiar with Python or C#. Comfortable with Docker and REST APIs.

### Secondary: AI/ML engineers building agent systems
- Building multi-agent workflows or chains (LangChain, LlamaIndex, custom).
- Need infrastructure for running agents reliably at scale.
- Care about DAG orchestration, concurrency control, and monitoring.

### Tertiary: Platform engineers supporting AI teams
- Setting up infrastructure for AI workloads.
- Evaluating queue systems, monitoring stacks, and deployment patterns.
- Care about Kubernetes, Helm, Prometheus, and operational concerns.

---

## SEO Keywords

### Primary keywords (target in titles and H2s)
- AI agent queue
- LLM orchestration
- AI agent production
- LangChain production
- AI workflow automation
- DAG workflow AI

### Secondary keywords (use naturally in body text)
- rate limit handling LLM
- dead letter queue AI
- AI agent retry logic
- OpenAI rate limit production
- AI code review automation
- AI agent monitoring
- queue-based AI architecture
- LLM concurrency control

### Long-tail keywords
- "how to handle OpenAI rate limits in production"
- "LangChain production reliability"
- "building AI agent pipelines with queues"
- "human approval gate AI workflow"
- "dead letter queue for failed AI tasks"

---

## Publishing Platforms

### Primary
| Platform | URL | Notes |
|----------|-----|-------|
| **dev.to** | https://dev.to | Largest developer community. Use tags: `ai`, `python`, `devops`, `tutorial`. Supports front matter natively. |
| **Hashnode** | https://hashnode.com | Strong SEO, supports custom domains. Use series feature for linked posts. |
| **Company blog** | (your domain) | Canonical URL should point here for SEO. Cross-post to dev.to and Hashnode with `canonical_url` set. |

### Secondary
| Platform | URL | Notes |
|----------|-----|-------|
| **Medium** | https://medium.com | Cross-post 1 week after primary. Set canonical URL. Use "Friend link" for non-paywalled access. |
| **Hacker News** | https://news.ycombinator.com | Submit post 1 only (most general appeal). Best on Tuesday–Thursday mornings. |
| **Reddit** | r/MachineLearning, r/Python, r/devops | Post as discussion, not self-promotion. Link in context of a genuine comment. |
| **LinkedIn** | https://linkedin.com | Short summary post with link. Target engineering managers and CTOs. |
| **Twitter/X** | https://x.com | Thread format: 5–7 tweets summarizing key points with link to full post. |

### Cross-posting checklist
- [ ] Set `canonical_url` in front matter to the primary (company blog) URL.
- [ ] Adjust relative links (e.g., quickstart guide) to absolute URLs.
- [ ] Add platform-specific tags/topics.
- [ ] Schedule cross-posts 2–3 days apart to avoid flooding.
- [ ] Track which platforms drive the most traffic (UTM parameters).

---

## Promotion Playbook

1. **Day 0** — Publish on company blog (canonical).
2. **Day 1** — Cross-post to dev.to with canonical URL.
3. **Day 2** — Cross-post to Hashnode.
4. **Day 3** — Twitter/X thread + LinkedIn summary.
5. **Day 5** — Submit to Hacker News (post 1 only) or relevant subreddits.
6. **Day 7** — Cross-post to Medium.
7. **Day 14** — Publish next post in series; link back to previous.

---

## File Structure

```
content/
├── blog/
│   ├── 01-why-ai-agents-need-a-queue.md
│   ├── 02-from-langchain-to-production.md
│   └── 03-building-code-review-pipeline.md
└── README.md          ← you are here
```
