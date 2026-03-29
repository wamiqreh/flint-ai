# Changelog

All notable changes to the Flint Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2025-07-14

### Added

- **Workflow Builder DSL** — fluent `Workflow` / `Node` API with `.depends_on()`, `.with_retries()`, `.requires_approval()`, `.dead_letter_on_failure()`, and `.with_metadata()`
- **DAG validation** — cycle detection (Kahn's algorithm), duplicate ID checks, and dangling dependency detection at build time
- **Batch task submission** — `submit_tasks()` for concurrent multi-task submission via `asyncio.gather()`
- **SSE streaming** — `stream_task()` for real-time task updates via Server-Sent Events
- **Metrics streaming** — `stream_metrics()` for periodic metrics snapshots
- **Automatic retries** — exponential backoff with jitter for transient HTTP errors (429, 502, 503, 504); respects `Retry-After` headers
- **Typed exceptions** — `TaskNotFoundError`, `RateLimitError`, `AuthenticationError`, `WorkflowValidationError`, `ConnectionError`
- **LangChain adapter** — `LangChainOrchestratorRunnable` for drop-in LangChain pipeline integration
- **CLI** (`flint`) — `submit`, `status`, `workflows list`, `workflows start` commands via Typer
- **Synchronous client** — `OrchestratorClient` wrapper for non-async codebases
- Full Pydantic v2 models with PascalCase alias serialization for API compatibility
- PyPI packaging with `[cli]` and `[langchain]` optional extras

### Changed

- Bumped minimum Python version to 3.9
- Improved project metadata and classifiers for PyPI

## [0.1.0] — 2025-06-01

### Added

- Initial release
- `AsyncOrchestratorClient` with `submit_task`, `get_task`, `wait_for_task`
- `create_workflow`, `start_workflow`, `list_workflows` workflow management
- Pydantic models: `SubmitTaskRequest`, `TaskResponse`, `WorkflowDefinition`, `WorkflowNode`, `WorkflowEdge`
- Basic HTTP error handling
