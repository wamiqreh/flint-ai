"""Fluent DSL for building workflow definitions programmatically.

Example::

    from flint_ai import Workflow, Node

    wf = (Workflow("code-review-pipeline")
        .add(Node("generate", agent="openai", prompt="Write code for {task}"))
        .add(Node("lint", agent="dummy", prompt="Lint the output").depends_on("generate"))
        .add(Node("test", agent="dummy", prompt="Run tests").depends_on("lint"))
        .add(Node("review", agent="claude", prompt="Review this code")
             .depends_on("test")
             .requires_approval()
             .with_retries(3)
             .dead_letter_on_failure())
        .build())
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Set

from .models import WorkflowDefinition, WorkflowEdge, WorkflowNode


class Node:
    """Builder for a single workflow node.

    Args:
        id: Unique node identifier within the workflow.
        agent: The agent type that will execute this node.
        prompt: The prompt template sent to the agent.
    """

    def __init__(self, id: str, agent: str, prompt: str) -> None:
        self._id = id
        self._agent = agent
        self._prompt = prompt
        self._dependencies: List[str] = []
        self._max_retries: int = 3
        self._dead_letter: bool = True
        self._human_approval: bool = False
        self._metadata: Dict[str, Any] = {}

    # -- chaining helpers ----------------------------------------------------

    def depends_on(self, *node_ids: str) -> Node:
        """Declare upstream dependencies for this node."""
        self._dependencies.extend(node_ids)
        return self

    def requires_approval(self) -> Node:
        """Require human approval before this node executes."""
        self._human_approval = True
        return self

    def with_retries(self, n: int) -> Node:
        """Set the maximum number of retry attempts."""
        if n < 0:
            raise ValueError("Retry count must be non-negative")
        self._max_retries = n
        return self

    def dead_letter_on_failure(self) -> Node:
        """Send to dead-letter queue on final failure."""
        self._dead_letter = True
        return self

    def with_metadata(self, **kwargs: Any) -> Node:
        """Attach arbitrary key-value metadata to the node."""
        self._metadata.update(kwargs)
        return self

    # -- conversion ----------------------------------------------------------

    def _to_workflow_node(self) -> WorkflowNode:
        """Convert to the Pydantic ``WorkflowNode`` model."""
        return WorkflowNode(
            Id=self._id,
            AgentType=self._agent,
            PromptTemplate=self._prompt,
            MaxRetries=self._max_retries,
            DeadLetterOnFailure=self._dead_letter,
            HumanApproval=self._human_approval,
        )

    def __repr__(self) -> str:
        deps = f", depends_on={self._dependencies!r}" if self._dependencies else ""
        return f"Node({self._id!r}, agent={self._agent!r}{deps})"


class Workflow:
    """Fluent builder that assembles a :class:`WorkflowDefinition`.

    Args:
        id: Unique workflow identifier.
    """

    def __init__(self, id: str) -> None:
        self._id = id
        self._nodes: List[Node] = []

    # -- chaining helpers ----------------------------------------------------

    def add(self, node: Node) -> Workflow:
        """Append a :class:`Node` to the workflow (returns *self* for chaining)."""
        self._nodes.append(node)
        return self

    # -- validation ----------------------------------------------------------

    def _validate(self) -> None:
        """Check for duplicate IDs, dangling references, and cycles."""
        node_ids: Set[str] = set()

        # Duplicate IDs
        for node in self._nodes:
            if node._id in node_ids:
                raise ValueError(f"Duplicate node id: {node._id!r}")
            node_ids.add(node._id)

        # Dangling dependency references
        for node in self._nodes:
            for dep in node._dependencies:
                if dep not in node_ids:
                    raise ValueError(
                        f"Node {node._id!r} depends on {dep!r} which does not exist"
                    )

        # Cycle detection (Kahn's algorithm)
        in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
        adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        for node in self._nodes:
            for dep in node._dependencies:
                adj[dep].append(node._id)
                in_degree[node._id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for neighbour in adj[current]:
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if visited != len(node_ids):
            raise ValueError("Workflow contains a cycle")

    # -- build ---------------------------------------------------------------

    def build(self) -> WorkflowDefinition:
        """Validate the workflow and return a :class:`WorkflowDefinition`."""
        self._validate()

        wf_nodes = [n._to_workflow_node() for n in self._nodes]

        wf_edges: List[WorkflowEdge] = []
        for node in self._nodes:
            for dep in node._dependencies:
                wf_edges.append(
                    WorkflowEdge(FromNodeId=dep, ToNodeId=node._id)
                )

        return WorkflowDefinition(
            Id=self._id,
            Nodes=wf_nodes,
            Edges=wf_edges,
        )

    # -- serialisation helpers -----------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Build and serialise to a plain dict (alias-keyed for the API)."""
        return self.build().model_dump(by_alias=True)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Build and serialise to a JSON string (alias-keyed for the API)."""
        return json.dumps(self.to_dict(), indent=indent)

    def __repr__(self) -> str:
        node_ids = [n._id for n in self._nodes]
        return f"Workflow({self._id!r}, nodes={node_ids!r})"


# Alias for discoverability
WorkflowBuilder = Workflow
