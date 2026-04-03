"""XCom-style context for data passing between workflow nodes.

Inspired by Airflow's XCom, this allows nodes to push/pull data
to/from a shared context within a workflow run.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("flint.server.dag.context")


class WorkflowContext:
    """Manages data passing between nodes in a workflow run.

    Data is organized by node_id and optional key. Nodes can:
    - push(key, value): Store data for downstream nodes
    - pull(node_id, key): Retrieve data from an upstream node
    - pull_all(node_id): Get all data from an upstream node
    - get_upstream_outputs(node_id, edges): Get all upstream results

    The context is serialized to JSON for persistence.
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data or {}

    def push(self, node_id: str, key: str, value: Any) -> None:
        """Push a value into the context for a given node."""
        if node_id not in self._data:
            self._data[node_id] = {}
        self._data[node_id][key] = value
        logger.debug("Context push: node=%s key=%s", node_id, key)

    def push_result(self, node_id: str, result: str, metadata: dict | None = None) -> None:
        """Push the full result of a node execution."""
        if node_id not in self._data:
            self._data[node_id] = {}
        self._data[node_id]["__result__"] = result
        if metadata:
            self._data[node_id]["__metadata__"] = metadata

    def pull(self, node_id: str, key: str, default: Any = None) -> Any:
        """Pull a specific value from a node's context."""
        return self._data.get(node_id, {}).get(key, default)

    def pull_result(self, node_id: str) -> str | None:
        """Pull the result output from a node."""
        return self._data.get(node_id, {}).get("__result__")

    def pull_all(self, node_id: str) -> dict[str, Any]:
        """Pull all data from a node's context."""
        return dict(self._data.get(node_id, {}))

    def get_upstream_results(self, upstream_node_ids: list[str]) -> dict[str, str]:
        """Get results from all upstream nodes."""
        results: dict[str, str] = {}
        for nid in upstream_node_ids:
            result = self.pull_result(nid)
            if result is not None:
                results[nid] = result
        return results

    def build_enriched_prompt(
        self, prompt_template: str, upstream_node_ids: list[str]
    ) -> str:
        """Build an enriched prompt by injecting upstream outputs.

        Supports two modes:
        1. Template variables: {node_id} gets replaced with that node's result
        2. Auto-prepend: If no template vars, prepend upstream outputs
        """
        import re

        prompt = prompt_template

        # Check for template variables like {step1} or {step1.key}
        pattern = r"\{(\w+)(?:\.(\w+))?\}"
        has_vars = bool(re.search(pattern, prompt))

        if has_vars:
            def replace_var(match: re.Match) -> str:
                nid = match.group(1)
                key = match.group(2)
                val = self.pull(nid, key) if key else self.pull_result(nid)
                return str(val) if val is not None else match.group(0)

            prompt = re.sub(pattern, replace_var, prompt)
        else:
            # Auto-prepend upstream outputs
            upstream_results = self.get_upstream_results(upstream_node_ids)
            if upstream_results:
                parts = []
                for nid, result in upstream_results.items():
                    parts.append(f"[Output from {nid}]:\n{result}")
                upstream_text = "\n\n---\n\n".join(parts)
                prompt = f"{upstream_text}\n\n---\n\n{prompt}"

        return prompt

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to a dict for persistence."""
        return dict(self._data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Deserialize context from a dict."""
        return cls(data=data)

    def merge(self, other: WorkflowContext) -> None:
        """Merge another context into this one."""
        for node_id, node_data in other._data.items():
            if node_id not in self._data:
                self._data[node_id] = {}
            self._data[node_id].update(node_data)
