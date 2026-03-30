"""Tool decorator for Flint OpenAI adapter.

Wraps functions as OpenAI-compatible tool definitions.
If the OpenAI Agents SDK is available, uses its @function_tool decorator
under the hood. Otherwise, generates tool schemas from type hints.
"""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable, Optional, get_type_hints


def tool(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable:
    """Decorator to mark a function as an OpenAI-compatible tool.

    Wraps the OpenAI Agents SDK @function_tool if available,
    otherwise generates the tool schema from type hints.

    Usage:
        @tool
        def search_code(query: str, language: str = "python") -> str:
            '''Search the codebase for matching code.'''
            ...

        @tool(name="analyze", description="Analyze a code diff")
        def analyze_diff(diff: str) -> str:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        tool_desc = description or fn.__doc__ or f"Tool: {tool_name}"

        # Try to use OpenAI Agents SDK's function_tool
        try:
            from agents import function_tool  # type: ignore[import-untyped]
            wrapped = function_tool(fn)
            wrapped._flint_tool = True
            wrapped._flint_tool_name = tool_name
            wrapped._flint_tool_schema = _build_schema(fn, tool_name, tool_desc)
            return wrapped
        except ImportError:
            pass

        # Fallback: generate schema ourselves
        fn._flint_tool = True  # type: ignore[attr-defined]
        fn._flint_tool_name = tool_name  # type: ignore[attr-defined]
        fn._flint_tool_schema = _build_schema(fn, tool_name, tool_desc)  # type: ignore[attr-defined]
        return fn

    if func is not None:
        return decorator(func)
    return decorator


def _python_type_to_json_type(py_type: Any) -> str:
    """Map Python types to JSON Schema types."""
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    return mapping.get(py_type, "string")


def _build_schema(fn: Callable, name: str, description: str) -> dict[str, Any]:
    """Build an OpenAI function tool schema from a Python function."""
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        param_type = hints.get(param_name, str)
        prop: dict[str, Any] = {"type": _python_type_to_json_type(param_type)}

        # Extract description from docstring param lines if possible
        if fn.__doc__:
            for line in fn.__doc__.split("\n"):
                line = line.strip()
                if line.startswith(f"{param_name}:") or line.startswith(f"{param_name} "):
                    prop["description"] = line.split(":", 1)[-1].strip() if ":" in line else line
                    break

        properties[param_name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description.strip(),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def get_tool_schemas(tools: list[Callable]) -> list[dict[str, Any]]:
    """Extract OpenAI function schemas from a list of @tool-decorated functions."""
    schemas = []
    for fn in tools:
        if hasattr(fn, "_flint_tool_schema"):
            schemas.append(fn._flint_tool_schema)
    return schemas


async def execute_tool_call(
    tools: list[Callable],
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """Execute a tool call by name and return the result as a string."""
    for fn in tools:
        fn_name = getattr(fn, "_flint_tool_name", getattr(fn, "__name__", None))
        if fn_name == tool_name:
            if inspect.iscoroutinefunction(fn):
                result = await fn(**arguments)
            else:
                result = fn(**arguments)
            return str(result) if not isinstance(result, str) else result

    return json.dumps({"error": f"tool_not_found: {tool_name}"})
