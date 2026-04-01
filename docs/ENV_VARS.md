## Environment Variables

### AI Provider Keys

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | For OpenAI adapter | OpenAI API key |
| `OPENAI_MODEL` | No | Model name (default: `gpt-4o-mini`) |

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | (in-memory) | Redis connection URL for production queue |
| `POSTGRES_URL` | (in-memory) | Postgres connection URL for production store |
| `WORKER_COUNT` | `4` | Number of background worker threads |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CONCURRENCY_openai` | `5` | Max concurrent OpenAI API calls |

### Webhook

| Variable | Description |
|----------|-------------|
| `TASK_COMPLETION_WEBHOOK_URL` | URL to receive task completion callbacks |
| `TASK_COMPLETION_WEBHOOK_BEARER_TOKEN` | Bearer token for webhook auth |

### Security

| Variable | Description |
|----------|-------------|
| `ORCHESTRATOR_API_KEY` | When set, all non-health endpoints require `X-API-Key` header |

> **Secrets:** For development, environment variables are fine. For production, use a secrets manager (AWS Secrets Manager, Azure Key Vault, HashiCorp Vault) and inject at deploy time. Never commit API keys to source control.

