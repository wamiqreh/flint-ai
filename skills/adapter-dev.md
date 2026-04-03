# Skill: Adapter Development

Load when: creating new adapters, integrating new LLM providers, modifying adapter system.

## Adapter Location

`flint_ai/adapters/` — SDK-side, runs on CLIENT machine with user's API keys.

## Creating a New Adapter

### 1. Directory structure
```
flint_ai/adapters/{provider}/
  __init__.py
  agent.py        # Main adapter class
  tools.py        # Optional: function calling support
```

### 2. Subclass FlintAdapter
```python
from flint_ai.adapters.core.base import FlintAdapter
from flint_ai.adapters.core.types import AgentRunResult, ErrorMapping, AdapterConfig

class MyAdapter(FlintAdapter):
    def __init__(
        self,
        name: str,
        model: str = "default-model",
        api_key: str | None = None,
    ):
        super().__init__(
            name=name,
            config=AdapterConfig(
                max_retries=3,
                human_approval=False,
                inline=True,
            ),
        )
        self.model = model
        self.api_key = api_key

    async def run(self, input_data: dict) -> AgentRunResult:
        try:
            result = await self._call_llm(input_data["prompt"])
            return AgentRunResult(output=result, success=True)
        except RateLimitError:
            return AgentRunResult(
                output="",
                success=False,
                error="rate limited",
                metadata={"error_action": "retry"},
            )
        except InvalidRequestError:
            return AgentRunResult(
                output="",
                success=False,
                error="invalid request",
                metadata={"error_action": "fail"},
            )

    async def _call_llm(self, prompt: str) -> str:
        # Implement your LLM call here
        raise NotImplementedError
```

### 3. Key return values

| error_action | Behavior |
|--------------|----------|
| `"retry"` (default) | Retries with backoff |
| `"dlq"` | Sends to dead-letter queue |
| `"fail"` | Immediate failure, no retry |

### 4. Error mapping (declarative)
```python
error_mapping = ErrorMapping(
    retry_on=[RateLimitError, TimeoutError],
    fail_on=[InvalidRequestError, AuthenticationError],
)
```

### 5. Registration
```python
from flint_ai.adapters.core.registry import register_inline

adapter = MyAdapter(name="my-agent")
register_inline(adapter)
```

### 6. With tools/function calling
See `flint_ai/adapters/openai/tools.py` for `@tool` decorator pattern.

## Reference Implementations

| File | What it shows |
|------|--------------|
| `flint_ai/adapters/openai/agent.py` | Full OpenAI adapter with tools |
| `flint_ai/adapters/openai/tools.py` | `@tool` decorator for function calling |
| `flint_ai/langchain_adapter.py` | LangChain integration |
| `flint_ai/crewai_adapter.py` | CrewAI integration |

## Testing

Add tests to `tests/test_adapters.py`. Pattern:
```python
class MockAdapter(FlintAdapter):
    async def run(self, input_data: dict) -> AgentRunResult:
        return AgentRunResult(output=f"echo: {input_data['prompt']}", success=True)
```

## Important

- Adapter runs on CLIENT, not server
- API key passed at construction, never sent to server
- `input_data` always has at least `{"prompt": "..."}`
- May also contain `task_id`, `workflow_id`, `metadata`
- Use `safe_run()` wrapper (inherited) for automatic error mapping
