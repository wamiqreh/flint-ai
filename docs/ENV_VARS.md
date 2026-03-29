Required environment variables

- COPILOT_API_KEY: API key for Copilot integration. If not provided, CopilotAgent runs in stub mode.
- COPILOT_API_URL: Optional override for Copilot API endpoint. Default: https://api.copilot.example/v1/generate
- CLAUDE_API_KEY: API key for Claude integration. If not provided, ClaudeAgent runs in stub mode.
- CLAUDE_API_URL: Optional override for Claude API endpoint. Default: https://api.anthropic.example/v1/complete
- CLAUDE_MODEL: Claude model for real Anthropic requests. Default: claude-3-5-haiku-latest
- CLAUDE_API_VERSION: Anthropic API version header. Default: 2023-06-01
- OPENAI_API_KEY: API key for OpenAI integration. If set, `openai` agent type is available.
- OPENAI_API_URL: Optional override for OpenAI endpoint. Default: https://api.openai.com/v1/chat/completions
- OPENAI_MODEL: OpenAI model name. Default: gpt-4o-mini
- TASK_COMPLETION_WEBHOOK_URL: Optional URL to receive task terminal state callbacks (Succeeded/Failed).
- TASK_COMPLETION_WEBHOOK_BEARER_TOKEN: Optional Bearer token attached to webhook callback requests.
- ORCHESTRATOR_API_KEY: Optional shared API key. When set, non-health/metrics/swaggger endpoints require `X-API-Key` header.

Secrets guidance

- For development, environment variables are acceptable. For production, use a secrets manager (Azure Key Vault / AWS Secrets Manager / HashiCorp Vault) and inject secrets into the runtime at deployment time.
- Do NOT commit API keys into source control or plan.md.

