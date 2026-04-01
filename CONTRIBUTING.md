# Contributing to Flint

Welcome! 🎉 Every contribution matters — bugs, features, docs, or plugins.

---

## Setup

```bash
git clone https://github.com/wamiqreh/flint-ai.git
cd flint-ai
pip install -e ".[all]"
pytest
```

## Run locally

```bash
# Embedded mode (no infrastructure needed):
python examples/demo.py

# With Redis + Postgres:
docker compose up -d
python -m flint_ai.server --port 5156
```

---

## Pull requests

1. **Branch** from `main`: `git checkout -b feature/my-feature`
2. **Commit** with [Conventional Commits](https://www.conventionalcommits.org/): `feat(dag): add conditional edges`
3. **Test**: `pytest` — all tests must pass
4. **PR**: fill out the template, link related issues

---

## Code style

- Python — follow PEP 8, use type hints
- Use `pydantic` for models, `httpx` for HTTP
- Use `ILogger`-style structured logging (`logging.getLogger(__name__)`)
- Tests go in `tests/` mirroring the source structure

---

## Adding an agent adapter

Create a new adapter in `flint_ai/adapters/`:

```python
from flint_ai.adapters.core.base import BaseAdapter

class MyAdapter(BaseAdapter):
    name = "my-agent"

    async def execute(self, prompt: str, **kwargs) -> str:
        # Call your AI API here
        return result
```

Register it with the engine:

```python
engine.register_adapter("my-agent", MyAdapter())
```

---

## Community

| Channel | Purpose |
|---------|---------|
| [GitHub Issues](../../issues) | Bugs and feature requests |
| [GitHub Discussions](../../discussions) | Questions and ideas |
