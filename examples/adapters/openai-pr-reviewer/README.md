# OpenAI PR Reviewer — Flint Adapter Example

A complete code review pipeline using Flint + OpenAI.

## What it does

```
generate (gpt-4o-mini) → review (gpt-4o + tools) → summarize (gpt-4o-mini)
                          ↑ human approval gate
```

1. **Generate** — GPT-4o-mini writes Python code based on a prompt
2. **Review** — GPT-4o reviews the code using tools (security checker, diff analyzer, line counter)
3. **Summarize** — GPT-4o-mini produces an executive summary

The review node requires **human approval** before it starts — you approve it from the Flint dashboard.

## Run it

```bash
# Install
pip install flint-ai[openai]

# Start Flint
docker compose -f docker-compose.dev.yml up -d

# Set your API key
export OPENAI_API_KEY=sk-...

# Run the pipeline
python main.py
```

Then open http://localhost:5156/dashboard/index.html to watch it execute and approve the review step.

## Key concepts

- **`FlintOpenAIAgent`** — wraps OpenAI as a Flint agent with natural syntax
- **`@tool`** — decorator for OpenAI-compatible function tools
- **`Node(agent=adapter_object)`** — pass adapter objects directly, not strings
- **`client.deploy_workflow(wf)`** — one call to register, create, and start
