# Good First Issues

This document lists well-scoped issues that are ideal for new contributors. Each issue is designed to help you get familiar with the codebase while making a meaningful contribution.

If you'd like to work on one of these, please comment on the corresponding GitHub issue (or create one from this list) so others know it's being worked on.

---

## Legend

| Difficulty | Meaning |
|-----------|---------|
| 🟢 Beginner | Minimal codebase knowledge needed; mostly isolated changes |
| 🟡 Intermediate | Requires understanding of one or two project modules |
| 🟠 Advanced Beginner | Touches multiple files or requires understanding patterns used in the project |

---

## Issues

### 1. Add XML Documentation Comments to Public API Endpoints

**Difficulty:** 🟢 Beginner  
**Description:** Several public API endpoints in `Orchestrator.Api` are missing XML doc comments. Add `<summary>`, `<param>`, and `<returns>` documentation to all public controller/endpoint methods so they appear correctly in Swagger/OpenAPI.  
**Files to look at:**
- `src/Orchestrator.Api/` — endpoint definitions  
**Skills:** C#, XML documentation

---

### 2. Add Unit Tests for DAG Cycle Detection

**Difficulty:** 🟡 Intermediate  
**Description:** The DAG workflow engine validates that workflows don't contain cycles, but test coverage is incomplete. Add unit tests covering: simple cycle (A→B→A), complex cycle (A→B→C→A), self-referencing node, and valid DAGs with diamond dependencies.  
**Files to look at:**
- `src/Orchestrator.Core/` — workflow/DAG validation logic
- `tests/Orchestrator.Core.Tests/` — existing test patterns  
**Skills:** C#, xUnit, graph theory basics

---

### 3. Improve Error Messages for Invalid Workflow YAML

**Difficulty:** 🟢 Beginner  
**Description:** When a user submits an invalid workflow template (e.g., missing required fields, invalid YAML syntax), the error messages are generic. Improve them to include the specific field that's invalid, the line number if possible, and a suggestion for how to fix it.  
**Files to look at:**
- `src/Orchestrator.Core/` — workflow parsing/validation  
- `templates/` — example workflow templates for reference  
**Skills:** C#, YAML, error handling

---

### 4. Add Health Check Endpoint for Queue Backend

**Difficulty:** 🟡 Intermediate  
**Description:** Add a `/health/queue` endpoint that reports the health status of the configured queue backend (In-Memory, Redis, or Kafka). It should return `healthy`, `degraded`, or `unhealthy` with details.  
**Files to look at:**
- `src/Orchestrator.Api/` — existing health check endpoints
- `src/Orchestrator.Infrastructure/` — queue backend implementations  
**Skills:** C#, ASP.NET Core health checks

---

### 5. Create a "Hello World" Workflow Template

**Difficulty:** 🟢 Beginner  
**Description:** Create a simple example workflow template that demonstrates the basics: two sequential tasks using the dummy agent, with a human approval gate between them. Include a README explaining the template.  
**Files to look at:**
- `templates/` — existing templates for format reference
- `docs/` — documentation structure  
**Skills:** YAML, Markdown

---

### 6. Add Retry Count to Task Status Response

**Difficulty:** 🟢 Beginner  
**Description:** When querying task status via `GET /tasks/{id}`, the response doesn't include how many times the task has been retried. Add a `retryCount` field to the task status response DTO.  
**Files to look at:**
- `src/Orchestrator.Api/` — task status endpoint and response models
- `src/Orchestrator.Core/` — task entity/model  
**Skills:** C#, REST API design

---

### 7. Add Docker Compose Healthcheck for Redis

**Difficulty:** 🟢 Beginner  
**Description:** The `docker-compose.dev.yml` file starts Redis but doesn't include a healthcheck. Add a proper healthcheck using `redis-cli ping` so dependent services wait for Redis to be ready.  
**Files to look at:**
- `docker-compose.dev.yml`
- `docker-compose.yml` — for reference on existing healthcheck patterns  
**Skills:** Docker, Docker Compose, YAML

---

### 8. Add Request Validation for Task Submission

**Difficulty:** 🟡 Intermediate  
**Description:** The `POST /tasks` endpoint accepts task submissions but doesn't validate all fields thoroughly. Add FluentValidation (or minimal API validation) for: non-empty agent name, valid priority range, payload size limits, and valid callback URL format.  
**Files to look at:**
- `src/Orchestrator.Api/` — task submission endpoint
- `src/Orchestrator.Core/` — task models  
**Skills:** C#, ASP.NET Core, validation

---

### 9. Add Prometheus Metrics for Workflow Completion

**Difficulty:** 🟡 Intermediate  
**Description:** The project has Prometheus metrics for individual tasks but is missing metrics for workflow-level events. Add counters for: `workflows_started_total`, `workflows_completed_total`, `workflows_failed_total`, and a histogram for `workflow_duration_seconds`.  
**Files to look at:**
- `src/Orchestrator.Core/` — workflow execution logic
- `src/Orchestrator.Infrastructure/` — existing Prometheus metric definitions
- `monitoring/` — Grafana dashboards and Prometheus config  
**Skills:** C#, Prometheus, metrics

---

### 10. Document All Environment Variables

**Difficulty:** 🟢 Beginner  
**Description:** Create a comprehensive table in the docs listing every environment variable the application reads, with its purpose, default value, required/optional status, and example. Cross-reference with `.env.example`.  
**Files to look at:**
- `.env.example`
- `src/Orchestrator.Api/` — configuration binding
- `docs/` — existing documentation  
**Skills:** Markdown, documentation

---

### 11. Add Python SDK Example for Workflow Submission

**Difficulty:** 🟡 Intermediate  
**Description:** The Python SDK exists but lacks an example showing how to define and submit a multi-step workflow (DAG). Add an `examples/python/workflow_example.py` that creates a 3-step workflow with dependencies and submits it.  
**Files to look at:**
- `sdks/` — existing SDK code
- `examples/` — existing examples  
**Skills:** Python, REST APIs

---

### 12. Add Git Pre-commit Hook for Build Verification

**Difficulty:** 🟢 Beginner  
**Description:** Add a Git pre-commit hook (using a shell script in `tools/`) that runs `dotnet build --warnaserror` before allowing a commit. Include setup instructions in `CONTRIBUTING.md`.  
**Files to look at:**
- `tools/` — existing tooling scripts
- `CONTRIBUTING.md` — contributing guide  
**Skills:** Shell scripting, Git hooks

---

### 13. Improve Logging in Worker Task Execution

**Difficulty:** 🟡 Intermediate  
**Description:** The worker logs when a task starts and finishes, but doesn't log intermediate steps like agent selection, retry attempts, or DLQ routing. Add structured log entries (using Serilog) at key decision points in the task execution pipeline.  
**Files to look at:**
- `src/Orchestrator.Worker/` — task execution pipeline
- `src/Orchestrator.Core/` — retry and DLQ logic  
**Skills:** C#, Serilog, structured logging

---

### 14. Add Helm Values Documentation

**Difficulty:** 🟢 Beginner  
**Description:** The Helm chart in `helm/` has a `values.yaml` but lacks a `README.md` that documents each configurable value. Generate or write a values reference document with descriptions, types, and defaults.  
**Files to look at:**
- `helm/` — Helm chart files
- `docs/` — documentation structure  
**Skills:** Markdown, Helm/Kubernetes basics

---

### 15. Create Integration Test for Redis Queue Backend

**Difficulty:** 🟠 Advanced Beginner  
**Description:** Add an integration test that verifies the full task lifecycle (enqueue → dequeue → process → complete) using the Redis Streams queue backend. Use the `docker-compose.integration.yml` setup.  
**Files to look at:**
- `tests/Orchestrator.Integration.Tests/` — existing integration tests
- `src/Orchestrator.Infrastructure/` — Redis queue backend implementation
- `docker-compose.integration.yml` — test infrastructure  
**Skills:** C#, xUnit, Redis, Docker

---

## How to Get Started

1. **Pick an issue** from the list above
2. **Comment on the GitHub issue** (or create one) to let others know you're working on it
3. **Read the [Contributing Guide](../CONTRIBUTING.md)** for setup and PR instructions
4. **Ask for help** in [Discord](https://discord.gg/PLACEHOLDER) `#contributing` or [GitHub Discussions](../../discussions) if you get stuck
5. **Submit your PR** — we review within 48 hours!

First-time contributors get a special shoutout in our release notes. 🎉
