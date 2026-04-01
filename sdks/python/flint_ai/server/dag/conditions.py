"""Conditional edge evaluation for DAG workflows.

Supports:
1. Status-based conditions (fire only on success/failure/etc.)
2. Expression-based conditions (Python expressions evaluated against upstream output)
3. Callback-based conditions (registered Python functions)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, Optional

from flint_ai.server.engine import EdgeCondition, TaskState

logger = logging.getLogger("flint.server.dag.conditions")

# Registry of named condition functions
_condition_registry: Dict[str, Callable[..., bool]] = {}


def register_condition(name: str, fn: Callable[..., bool]) -> None:
    """Register a named condition function for use in edge expressions."""
    _condition_registry[name] = fn


def get_condition(name: str) -> Optional[Callable[..., bool]]:
    return _condition_registry.get(name)


class ConditionEvaluator:
    """Evaluates edge conditions against upstream task results."""

    # Allowed builtins for safe expression evaluation
    SAFE_BUILTINS = {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "any": any,
        "all": all,
        "sorted": sorted,
        "isinstance": isinstance,
        "True": True,
        "False": False,
        "None": None,
    }

    def evaluate(
        self,
        condition: EdgeCondition,
        upstream_status: TaskState,
        upstream_result: Optional[str] = None,
        upstream_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluate whether an edge condition is met.

        Args:
            condition: The edge condition to evaluate.
            upstream_status: The state of the upstream task.
            upstream_result: The output/result string of the upstream task.
            upstream_metadata: Metadata from the upstream task.
            context: The workflow run context (XCom data).

        Returns:
            True if the edge should fire, False otherwise.
        """
        if condition.is_empty():
            # No condition = always fire on success
            return upstream_status == TaskState.SUCCEEDED

        # Status-based condition
        if condition.on_status:
            if upstream_status not in condition.on_status:
                return False

        # Expression-based condition
        if condition.expression:
            return self._eval_expression(
                condition.expression,
                upstream_status,
                upstream_result,
                upstream_metadata or {},
                context or {},
            )

        # If only status filter was set and it matched
        return True

    def _eval_expression(
        self,
        expr: str,
        status: TaskState,
        result: Optional[str],
        metadata: Dict[str, Any],
        context: Dict[str, Any],
    ) -> bool:
        """Safely evaluate a Python expression.

        Available variables:
        - result: str — upstream output
        - metadata: dict — upstream metadata
        - status: str — upstream task state
        - context: dict — workflow run context (XCom data)
        - Any registered condition functions
        """
        local_vars = {
            "result": result or "",
            "metadata": metadata,
            "status": status.value,
            "context": context,
            **_condition_registry,
        }

        try:
            # Use restricted globals to prevent arbitrary code execution
            safe_globals = {"__builtins__": self.SAFE_BUILTINS}
            return bool(eval(expr, safe_globals, local_vars))  # noqa: S307
        except Exception as e:
            logger.warning(
                "Condition expression failed: %r → %s (treating as False)", expr, e
            )
            return False


# Singleton evaluator
_evaluator = ConditionEvaluator()


def evaluate_condition(
    condition: EdgeCondition,
    upstream_status: TaskState,
    upstream_result: Optional[str] = None,
    upstream_metadata: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    """Module-level convenience function for condition evaluation."""
    return _evaluator.evaluate(
        condition, upstream_status, upstream_result, upstream_metadata, context
    )
