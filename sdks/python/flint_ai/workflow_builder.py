"""Fluent DSL for building workflow definitions programmatically.

Example::

    from flint_ai import Workflow, Node
    from flint_ai.adapters.openai import FlintOpenAIAgent

    results = (Workflow("my-pipeline")
        .add(Node("step1", agent=FlintOpenAIAgent(name="a1", model="gpt-4o-mini",
                  instructions="Do X"), prompt="..."))
        .add(Node("step2", agent=FlintOpenAIAgent(name="a2", model="gpt-4o-mini",
                  instructions="Do Y"), prompt="...").depends_on("step1"))
        .run()
    )
    print(results["step1"])
    print(results["step2"])
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Set

from .models import WorkflowDefinition, WorkflowEdge, WorkflowNode

logger = logging.getLogger("flint.workflow")


class Node:
    """Builder for a single workflow node.

    Args:
        id: Unique node identifier within the workflow.
        agent: The agent type (string) or a FlintAdapter instance.
        prompt: The prompt template sent to the agent.
    """

    def __init__(self, id: str, agent: Any, prompt: str) -> None:
        self._id = id
        self._prompt = prompt
        self._dependencies: List[str] = []
        self._max_retries: int = 3
        self._dead_letter: bool = True
        self._human_approval: bool = False
        self._metadata: Dict[str, Any] = {}
        self._adapter: Any = None

        # Accept either a string agent type or a FlintAdapter object
        if isinstance(agent, str):
            self._agent = agent
        else:
            # It's an adapter object — extract the name, store the reference
            self._adapter = agent
            self._agent = agent.get_agent_name()
            # Inherit config from adapter
            if hasattr(agent, 'config'):
                if agent.config.human_approval:
                    self._human_approval = True
                if agent.config.max_retries is not None:
                    self._max_retries = agent.config.max_retries
                if agent.config.dead_letter_on_failure is not None:
                    self._dead_letter = agent.config.dead_letter_on_failure

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

    @property
    def adapter(self) -> Any:
        """Return the FlintAdapter instance, if one was provided."""
        return self._adapter

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

    def get_adapters(self) -> list:
        """Return all FlintAdapter instances used by nodes in this workflow."""
        return [n._adapter for n in self._nodes if n._adapter is not None]

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

    # -- run (the whole point) -----------------------------------------------

    def run(
        self,
        *,
        base_url: str = "http://localhost:5156",
        worker_port: int = 5157,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        verbose: bool = True,
    ) -> Dict[str, str]:
        """Run the workflow end-to-end and return results.

        This is the primary user-facing API. It handles everything:
        worker startup, deployment, polling, cleanup.

        Returns:
            Dict mapping node_id → output string for each completed node.

        Raises:
            RuntimeError: If any node fails or the workflow times out.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an async context — can't use asyncio.run()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self.run_async(
                        base_url=base_url,
                        worker_port=worker_port,
                        poll_interval=poll_interval,
                        timeout=timeout,
                        verbose=verbose,
                    ),
                )
                return future.result()
        else:
            return asyncio.run(
                self.run_async(
                    base_url=base_url,
                    worker_port=worker_port,
                    poll_interval=poll_interval,
                    timeout=timeout,
                    verbose=verbose,
                )
            )

    async def run_async(
        self,
        *,
        base_url: str = "http://localhost:5156",
        worker_port: int = 5157,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        verbose: bool = True,
    ) -> Dict[str, str]:
        """Async version of :meth:`run`. Awaitable.

        Returns:
            Dict mapping node_id → output string for each completed node.
        """
        import time
        from .adapters.core.worker import start_worker, stop_worker
        from .client import AsyncOrchestratorClient

        # Auto-suffix workflow ID to avoid conflicts on re-runs
        run_id = f"{self._id}-{uuid.uuid4().hex[:6]}"
        original_id = self._id
        self._id = run_id

        try:
            # 1. Start worker
            await start_worker(port=worker_port)
            await asyncio.sleep(0.3)

            # 2. Deploy
            async with AsyncOrchestratorClient(base_url=base_url) as client:
                wf_id = await client.deploy_workflow(self)
                if verbose:
                    print(f"🔥 Flint — running workflow '{wf_id}' ({len(self._nodes)} nodes)")
                    print(f"   Dashboard: {base_url}/dashboard/index.html\n")

                # 3. Poll until all nodes complete
                node_ids = {n._id for n in self._nodes}
                agent_to_node = {}
                for n in self._nodes:
                    agent_to_node[n._agent] = n._id

                results: Dict[str, str] = {}
                failures: Dict[str, str] = {}
                t0 = time.time()

                while len(results) + len(failures) < len(node_ids):
                    if time.time() - t0 > timeout:
                        raise RuntimeError(
                            f"Workflow timed out after {timeout}s. "
                            f"Completed: {list(results.keys())}, "
                            f"Pending: {list(node_ids - results.keys() - failures.keys())}"
                        )

                    resp = await client._request(
                        "GET", "/tasks", params={"workflowId": wf_id}
                    )
                    for task in resp.json():
                        agent = task.get("agentType", "")
                        state = task.get("state", "")
                        node_id = agent_to_node.get(agent, agent)

                        if node_id in results or node_id in failures:
                            continue

                        if state == "Succeeded":
                            raw = task.get("result", "")
                            try:
                                output = json.loads(raw).get("Output", raw)
                            except Exception:
                                output = raw
                            results[node_id] = output
                            if verbose:
                                elapsed = time.time() - t0
                                preview = output[:120].replace("\n", " ")
                                print(f"  ✔ {node_id} — {elapsed:.0f}s — {preview}...")

                        elif state in ("Failed", "DeadLetter"):
                            error = task.get("result", task.get("error", "unknown"))
                            failures[node_id] = error
                            if verbose:
                                print(f"  ✘ {node_id} FAILED — {error[:120]}")

                    await asyncio.sleep(poll_interval)

                elapsed = time.time() - t0
                if verbose:
                    print(f"\n{'✅' if not failures else '⚠️'} Done in {elapsed:.0f}s")

                if failures:
                    raise RuntimeError(
                        f"Workflow failed. Failures: {failures}. "
                        f"Succeeded: {list(results.keys())}"
                    )

                return results

        finally:
            self._id = original_id
            await stop_worker()


# Alias for discoverability
WorkflowBuilder = Workflow
