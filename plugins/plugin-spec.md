# AQO Plugin Specification

**Version:** 1.0.0

This document defines the plugin format for Flint. All plugins
must conform to this specification to be installable via `flint plugins install`.

---

## 1. Plugin Manifest (`plugin.json`)

Every plugin **must** include a `plugin.json` at its root. This file describes the
plugin to the marketplace and the runtime loader.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `string` | Unique plugin identifier. Convention: `<type>-<name>` (e.g. `agent-gemini`). |
| `version` | `string` | Semantic version (`MAJOR.MINOR.PATCH`). |
| `type` | `string` | One of: `agent`, `template`, `middleware`. |
| `description` | `string` | Short description (max 200 chars). |
| `author` | `string` | GitHub username or organization. |
| `repository` | `string` | Git clone URL or GitHub repository URL. |
| `compatibility` | `string` | SemVer range of compatible AQO versions (e.g. `>=0.1.0`). |
| `entry_point` | `string` | Relative path to the main file (e.g. `agent.py`, `workflow.json`). |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `license` | `string` | SPDX license identifier (e.g. `MIT`, `Apache-2.0`). |
| `tags` | `string[]` | Keywords for search/discovery. |
| `dependencies` | `object` | Python package dependencies (`{"httpx": ">=0.24.0"}`). |
| `config_schema` | `object` | JSON Schema for plugin configuration (env vars, API keys). |
| `homepage` | `string` | URL to documentation or project page. |
| `min_python` | `string` | Minimum Python version (e.g. `3.10`). |

### Example Manifest

```json
{
  "name": "agent-gemini",
  "version": "0.1.0",
  "type": "agent",
  "description": "Google Gemini agent adapter for Flint",
  "author": "flint-community",
  "repository": "https://github.com/flint-plugins/agent-gemini",
  "compatibility": ">=0.1.0",
  "entry_point": "agent.py",
  "license": "MIT",
  "tags": ["google", "gemini", "llm", "generative-ai"],
  "dependencies": {
    "google-generativeai": ">=0.3.0"
  },
  "config_schema": {
    "type": "object",
    "properties": {
      "GOOGLE_API_KEY": {
        "type": "string",
        "description": "Google AI Studio API key"
      },
      "GEMINI_MODEL": {
        "type": "string",
        "default": "gemini-pro",
        "description": "Gemini model name"
      }
    },
    "required": ["GOOGLE_API_KEY"]
  }
}
```

---

## 2. Agent Plugins

Agent plugins add new AI model backends to AQO. They **must** implement the
`IAgent` interface pattern.

### Python Interface

```python
class IAgent:
    """Interface that all agent plugins must implement."""

    @property
    def agent_type(self) -> str:
        """Unique identifier for this agent (e.g. 'gemini')."""
        ...

    def execute(self, prompt: str, **kwargs) -> str:
        """Execute a prompt and return the result as a string.

        Args:
            prompt: The user prompt / task description.
            **kwargs: Optional context (task_id, workflow_id, metadata).

        Returns:
            The agent's response as a string.

        Raises:
            AgentExecutionError: If the agent fails to produce a result.
        """
        ...

    async def aexecute(self, prompt: str, **kwargs) -> str:
        """Async variant of execute. Optional — falls back to execute()
        in a thread pool if not implemented."""
        ...
```

### Requirements

1. The entry point file **must** define a class named `Agent` that implements the
   interface above.
2. `agent_type` **must** return a lowercase string matching the plugin name suffix
   (e.g. plugin `agent-gemini` → `agent_type = "gemini"`).
3. The `execute()` method **must** be synchronous. Provide `aexecute()` for async
   support.
4. Errors **must** raise `AgentExecutionError` (or a subclass) with a descriptive
   message.
5. Configuration (API keys, model names) **should** be read from environment
   variables or a config dict passed to `__init__`.

### Example

```python
import os

class Agent:
    """Google Gemini agent adapter."""

    def __init__(self, config: dict | None = None):
        self.api_key = (config or {}).get(
            "GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", "")
        )
        self.model = (config or {}).get("GEMINI_MODEL", "gemini-pro")

    @property
    def agent_type(self) -> str:
        return "gemini"

    def execute(self, prompt: str, **kwargs) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(prompt)
        return response.text
```

---

## 3. Template Plugins

Template plugins provide reusable workflow definitions that users can import.

### Requirements

1. The entry point **must** be a `workflow.json` file conforming to the
   `WorkflowDefinition` schema.
2. The workflow file **must** include:
   - `Id`: Unique workflow identifier.
   - `Nodes`: Array of `WorkflowNode` objects.
   - `Edges`: Array of `WorkflowEdge` objects defining the DAG.
3. Templates **may** use `{{variable}}` placeholders in `PromptTemplate` fields
   for user customization.

### WorkflowDefinition Schema

```json
{
  "Id": "string — unique workflow identifier",
  "Nodes": [
    {
      "Id": "string — unique node identifier",
      "AgentType": "string — agent to use (e.g. 'openai', 'dummy')",
      "PromptTemplate": "string — prompt with optional {{variable}} placeholders",
      "MaxRetries": "integer — default 3",
      "DeadLetterOnFailure": "boolean — default true",
      "HumanApproval": "boolean — default false"
    }
  ],
  "Edges": [
    {
      "FromNodeId": "string — source node Id",
      "ToNodeId": "string — target node Id",
      "Condition": "string — optional condition expression"
    }
  ]
}
```

### Example

```json
{
  "Id": "rag-pipeline",
  "Nodes": [
    {
      "Id": "retrieve",
      "AgentType": "openai",
      "PromptTemplate": "Retrieve relevant documents for: {{query}}"
    },
    {
      "Id": "generate",
      "AgentType": "openai",
      "PromptTemplate": "Based on these documents: {{retrieve.output}}\n\nAnswer: {{query}}"
    }
  ],
  "Edges": [
    { "FromNodeId": "retrieve", "ToNodeId": "generate" }
  ]
}
```

---

## 4. Middleware Plugins

Middleware plugins add request/response hooks to the task processing pipeline.

### Python Interface

```python
class Middleware:
    """Interface that all middleware plugins must implement."""

    def on_task_submitted(self, task: dict) -> dict:
        """Called when a task is submitted, before it enters the queue.

        Args:
            task: The task payload dict.

        Returns:
            The (possibly modified) task dict.
        """
        return task

    def on_task_completed(self, task: dict, result: str) -> str:
        """Called when a task completes, before the result is returned.

        Args:
            task: The original task payload.
            result: The agent's raw output.

        Returns:
            The (possibly modified) result string.
        """
        return result

    def on_task_failed(self, task: dict, error: Exception) -> None:
        """Called when a task fails.

        Args:
            task: The original task payload.
            error: The exception that caused the failure.
        """
        pass
```

### Requirements

1. The entry point file **must** define a class named `Middleware`.
2. All hook methods are optional — the base behavior is pass-through.
3. `on_task_submitted` **may** modify the task dict (e.g. add metadata, validate).
4. `on_task_completed` **may** transform the result (e.g. format, filter, cache).
5. Middleware runs in registration order; plugins are loaded alphabetically.

### Example Use Cases

- **Logging middleware**: Log all task submissions and completions.
- **Rate-limiting middleware**: Throttle submissions per agent type.
- **Caching middleware**: Return cached results for duplicate prompts.
- **PII redaction middleware**: Strip sensitive data before sending to agents.

---

## 5. Plugin Directory Structure

### Agent Plugin

```
agent-<name>/
├── plugin.json       # Plugin manifest (required)
├── README.md         # Usage documentation (required)
├── agent.py          # Agent implementation (required)
├── requirements.txt  # Python dependencies (optional)
└── tests/            # Plugin tests (recommended)
    └── test_agent.py
```

### Template Plugin

```
template-<name>/
├── plugin.json       # Plugin manifest (required)
├── README.md         # Usage documentation (required)
├── workflow.json     # Workflow definition (required)
└── examples/         # Example inputs/outputs (recommended)
```

### Middleware Plugin

```
middleware-<name>/
├── plugin.json       # Plugin manifest (required)
├── README.md         # Usage documentation (required)
├── middleware.py     # Middleware implementation (required)
└── tests/            # Plugin tests (recommended)
    └── test_middleware.py
```

---

## 6. Installation & Loading

### Installation

```bash
flint plugins install <name>
```

This clones the plugin repository into `~/.flint/plugins/<name>/` and installs
any Python dependencies listed in `plugin.json`.

### Plugin Resolution Order

1. Local project plugins: `./plugins/`
2. User plugins: `~/.flint/plugins/`
3. Built-in plugins (bundled with AQO)

### Loading

At startup, AQO scans plugin directories for `plugin.json` files and:

1. Validates the manifest against this spec.
2. Checks `compatibility` against the running AQO version.
3. Imports the `entry_point` module.
4. Registers the plugin:
   - **Agent**: Adds to the agent registry (`AgentRegistry`).
   - **Template**: Makes available via `flint workflows list`.
   - **Middleware**: Inserts into the processing pipeline.

---

## 7. Versioning & Compatibility

- Plugins **must** use [Semantic Versioning](https://semver.org/).
- The `compatibility` field uses npm-style semver ranges:
  - `>=0.1.0` — any version 0.1.0 or higher
  - `>=0.1.0 <1.0.0` — 0.x releases only
  - `~0.2.0` — patch-level changes within 0.2.x
- Breaking changes to the plugin API will bump the spec major version.

---

## 8. Security Considerations

- Plugins run with the same permissions as the AQO process.
- **Never** hardcode API keys in plugin source code. Use environment variables.
- Plugin authors **should** pin dependency versions to avoid supply-chain attacks.
- The registry only indexes plugins — it does not host code. Always review plugin
  source before installing.
