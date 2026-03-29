# Contributing to Flint

Welcome! 🎉 We're excited that you want to contribute to Flint. Whether you're fixing a bug, adding a feature, improving docs, or submitting a plugin — every contribution matters.

This guide will help you get started.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Environment Setup](#development-environment-setup)
- [How to Submit a Pull Request](#how-to-submit-a-pull-request)
- [Code Style Guidelines](#code-style-guidelines)
- [How to Report Bugs](#how-to-report-bugs)
- [How to Request Features](#how-to-request-features)
- [How to Add a New Agent Adapter](#how-to-add-a-new-agent-adapter)
- [How to Add a Workflow Template](#how-to-add-a-workflow-template)
- [Community Channels](#community-channels)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold a welcoming, inclusive, and harassment-free environment. Please read it before contributing.

---

## Development Environment Setup

### Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| [.NET SDK](https://dotnet.microsoft.com/download) | 8.0+ | Required for building and running the project |
| [Docker](https://docs.docker.com/get-docker/) | 24.0+ | Required for integration tests and local infrastructure |
| [Docker Compose](https://docs.docker.com/compose/) | 2.20+ | Bundled with Docker Desktop |
| [Git](https://git-scm.com/) | 2.40+ | Version control |
| [Redis](https://redis.io/) | 7.0+ | Optional — only if testing with Redis queue backend |
| [PostgreSQL](https://www.postgresql.org/) | 15+ | Optional — only if testing with durable persistence |

### Clone and Build

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/<your-username>/flint.git
cd flint

# Restore dependencies and build
dotnet restore
dotnet build

# Run unit tests
dotnet test tests/Orchestrator.Core.Tests/

# Run integration tests (requires Docker)
docker compose -f docker-compose.integration.yml up -d
dotnet test tests/Orchestrator.Integration.Tests/
docker compose -f docker-compose.integration.yml down
```

### Running Locally

```bash
# Start infrastructure (Redis, PostgreSQL, monitoring)
docker compose -f docker-compose.dev.yml up -d

# Run the API
dotnet run --project src/Orchestrator.Api/

# The API will be available at https://localhost:5001
```

### Environment Variables

Copy the example environment file and configure it for your local setup:

```bash
cp .env.example .env
```

---

## How to Submit a Pull Request

### 1. Fork and Branch

```bash
# Fork the repo on GitHub, then:
git checkout -b <type>/<short-description>
# Examples:
#   feature/kafka-dead-letter-queue
#   fix/redis-reconnect-timeout
#   docs/add-helm-guide
#   plugin/ollama-agent-adapter
```

### 2. Commit Conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

<optional body>

<optional footer>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `plugin`

**Scopes:** `core`, `api`, `worker`, `infrastructure`, `sdk`, `docker`, `helm`, `docs`

**Examples:**

```
feat(core): add Kafka dead-letter queue support
fix(worker): handle Redis reconnect timeout gracefully
docs(api): add OpenAPI endpoint descriptions
plugin(infrastructure): add Ollama agent adapter
test(core): add DAG cycle detection unit tests
```

### 3. Before Submitting

- [ ] All existing tests pass: `dotnet test`
- [ ] New code has tests (aim for >80% coverage on new code)
- [ ] No build warnings: `dotnet build --warnaserror`
- [ ] Code follows the project style guidelines (see below)
- [ ] Documentation is updated if behavior changed
- [ ] Commit messages follow Conventional Commits

### 4. Open the PR

- Fill out the [Pull Request template](.github/PULL_REQUEST_TEMPLATE.md) completely
- Link any related issues using `Closes #123` or `Fixes #123`
- Request a review from a maintainer
- Be responsive to feedback — we aim to review PRs within 48 hours

---

## Code Style Guidelines

### C# (.NET)

- Follow [Microsoft's C# coding conventions](https://learn.microsoft.com/en-us/dotnet/csharp/fundamentals/coding-style/coding-conventions)
- Use `file-scoped namespaces`
- Use `primary constructors` where appropriate (.NET 8+)
- Prefer `readonly` fields and `init` properties
- Use `ILogger<T>` for structured logging — never `Console.WriteLine`
- All public APIs must have XML doc comments
- Use `CancellationToken` on all async methods
- Prefer `ValueTask` over `Task` for hot paths

### Architecture Patterns

- **Adapter pattern** for queue backends — implement `IQueueBackend`
- **Strategy pattern** for agent adapters — implement `IAgent`
- **CQRS-like separation** in the API layer
- Keep `Orchestrator.Core` free of infrastructure dependencies

### Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Interfaces | `I` prefix | `IQueueBackend`, `IAgent` |
| Async methods | `Async` suffix | `EnqueueAsync`, `ExecuteAsync` |
| Test methods | `Method_Scenario_Expected` | `Enqueue_WhenQueueFull_ThrowsException` |
| Test classes | `ClassTests` | `TaskQueueServiceTests` |

---

## How to Report Bugs

1. **Search first** — check [existing issues](../../issues) to avoid duplicates
2. **Use the bug report template** — [File a bug report](../../issues/new?template=bug_report.yml)
3. **Include reproduction steps** — the more detail, the faster we can fix it
4. **Attach logs** — include relevant Serilog output, Prometheus metrics, or Docker logs
5. **Specify your environment** — OS, .NET version, Docker version, queue backend

---

## How to Request Features

1. **Search first** — check [existing issues](../../issues) and [discussions](../../discussions)
2. **Use the feature request template** — [Request a feature](../../issues/new?template=feature_request.yml)
3. **Describe the use case** — explain *why* you need it, not just *what* you want
4. **Consider alternatives** — mention other approaches you've considered

---

## How to Add a New Agent Adapter

Agent adapters allow the orchestrator to execute tasks on any AI backend. To add a new adapter:

### 1. Implement `IAgent`

Create a new class in `src/Orchestrator.Infrastructure/Agents/`:

```csharp
namespace Orchestrator.Infrastructure.Agents;

public class MyNewAgent : IAgent
{
    public string Name => "my-new-agent";

    public async ValueTask<AgentResult> ExecuteAsync(
        AgentTask task,
        CancellationToken cancellationToken = default)
    {
        // Your agent logic here
        // - Call external API
        // - Handle rate limiting (use Polly policies)
        // - Return structured result
    }
}
```

### 2. Register in DI

Add your agent to the service collection in `src/Orchestrator.Infrastructure/`:

```csharp
services.AddKeyedSingleton<IAgent, MyNewAgent>("my-new-agent");
```

### 3. Add Configuration

Add any required configuration to `appsettings.json`:

```json
{
  "Agents": {
    "MyNewAgent": {
      "ApiKey": "",
      "BaseUrl": "https://api.example.com",
      "MaxConcurrency": 5
    }
  }
}
```

### 4. Write Tests

Add unit tests in `tests/Orchestrator.Core.Tests/Agents/` and integration tests if the agent calls external APIs.

### 5. Document

- Add a section to `docs/` describing your agent adapter
- Update `README.md` if the agent is bundled (not a plugin)
- Submit your adapter as a [plugin submission](../../issues/new?template=plugin_submission.yml) if it's a community contribution

---

## How to Add a Workflow Template

Workflow templates are pre-built DAG definitions that users can instantiate. To add a new template:

### 1. Create the Template File

Add a YAML file to `templates/`:

```yaml
name: my-workflow-template
description: A short description of what this workflow does
version: "1.0"

nodes:
  - id: step-1
    agent: copilot
    prompt: "Do the first thing"
    
  - id: step-2
    agent: claude
    prompt: "Review the output of step 1"
    depends_on: [step-1]

  - id: approval
    type: human-approval
    depends_on: [step-2]

  - id: step-3
    agent: copilot
    prompt: "Final step after approval"
    depends_on: [approval]
```

### 2. Validate the Template

```bash
# Templates are validated on load — test by submitting:
curl -X POST https://localhost:5001/workflows \
  -H "Content-Type: application/json" \
  -d @templates/my-workflow-template.yaml
```

### 3. Add Documentation

Create a markdown file in `docs/templates/` describing:
- What the template does
- When to use it
- Required agents
- Input/output schema
- Example usage

### 4. Submit

Open a PR with the template file, documentation, and any tests.

---

## Community Channels

| Channel | Purpose |
|---------|---------|
| [GitHub Issues](../../issues) | Bug reports, feature requests, plugin submissions |
| [GitHub Discussions](../../discussions) | Questions, ideas, showcases, general conversation |
| [Discord](https://discord.gg/PLACEHOLDER) | Real-time chat with maintainers and community |

### Getting Help

- **Quick questions** → Discord `#help` channel or GitHub Discussions Q&A
- **Bug reports** → GitHub Issues with the bug report template
- **Feature ideas** → GitHub Discussions "Ideas" category or Discord `#ideas`
- **Plugin showcase** → Discord `#plugins` or GitHub Discussions "Show and Tell"

---

## Recognition

All contributors are recognized in our release notes. Significant contributions may earn you the **Contributor** role on Discord and a mention in the README.

Thank you for helping make Flint better! 🚀
