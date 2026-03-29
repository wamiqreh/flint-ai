# AQO Plugin Marketplace

Build, share, and install community plugins for Flint.

## Plugin Types

| Type | Description | Entry Point |
|------|-------------|-------------|
| **agent** | Adds a new AI agent backend (e.g. Gemini, Ollama) | `agent.py` implementing `IAgent` |
| **template** | Provides a reusable workflow definition | `workflow.json` |
| **middleware** | Adds request/response hooks to the pipeline | `middleware.py` implementing hooks |

## Quick Start

### Installing a Plugin

```bash
# List available plugins
flint plugins list

# Search for a specific plugin
flint plugins search "gemini"

# Install a plugin
flint plugins install agent-gemini

# View plugin details
flint plugins info agent-gemini
```

Plugins are installed to `~/.flint/plugins/<plugin-name>/`.

### Creating a Plugin

1. **Create a directory** with your plugin name (e.g. `agent-my-model/`)

2. **Add a `plugin.json` manifest:**

```json
{
  "name": "agent-my-model",
  "version": "0.1.0",
  "type": "agent",
  "description": "My custom AI agent adapter",
  "author": "your-github-username",
  "repository": "https://github.com/your-org/agent-my-model",
  "compatibility": ">=0.1.0",
  "entry_point": "agent.py",
  "license": "MIT",
  "tags": ["ai", "custom-model"]
}
```

3. **Implement the entry point** — see [plugin-spec.md](plugin-spec.md) for the full specification.

4. **Test locally:**

```bash
# Copy your plugin into the plugins directory
cp -r agent-my-model/ ~/.flint/plugins/

# Verify it's detected
flint plugins list --local
```

### Publishing a Plugin

1. Push your plugin to a public Git repository.
2. Open a Pull Request to this repository adding your plugin to `registry.json`.
3. Your PR should include:
   - An entry in `registry.json` with all required fields
   - A README documenting usage, configuration, and examples

### Registry Format

The central registry (`registry.json`) indexes all known plugins:

```json
{
  "version": "1",
  "plugins": [
    {
      "name": "agent-gemini",
      "type": "agent",
      "version": "0.1.0",
      "description": "Google Gemini agent adapter",
      "author": "flint-community",
      "repository": "https://github.com/flint-plugins/agent-gemini",
      "tags": ["google", "gemini", "llm"]
    }
  ]
}
```

## Examples

- [`examples/agent-gemini/`](examples/agent-gemini/) — Agent plugin for Google Gemini
- [`examples/template-rag/`](examples/template-rag/) — RAG pipeline workflow template

## Resources

- [Plugin Specification](plugin-spec.md) — Full technical spec for plugin authors
- [Registry](registry.json) — Browse all available plugins
- [CLI Reference](../docs-site/docs/cli-reference.md) — `flint plugins` commands
