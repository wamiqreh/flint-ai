"""Fluent DSL for building and running workflow DAGs.

Example::

    from flint_ai import Workflow, Node
    from flint_ai.adapters.openai import FlintOpenAIAgent

    researcher = FlintOpenAIAgent(name="researcher", model="gpt-4o-mini",
                                  instructions="Research the topic. Return key findings.",
                                  response_format={"type": "json_object"})
    writer     = FlintOpenAIAgent(name="writer", model="gpt-4o-mini",
                                  instructions="Write a polished summary from the research.")
    reviewer   = FlintOpenAIAgent(name="reviewer", model="gpt-4o-mini",
                                  instructions="Review the article. Score out of 10.",
                                  response_format={"type": "json_object"})

    results = (
        Workflow("demo")
        .add(Node("research", agent=researcher, prompt="AI orchestration 2025"))
        .add(Node("write", agent=writer, prompt="Summarize the research").depends_on("research"))
        .add(Node("review", agent=reviewer, prompt="Review this article").depends_on("write"))
        .run()
    )

    print(results["research"])   # structured JSON from GPT
    print(results["write"])      # article text
    print(results["review"])     # scored review JSON
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from typing import Any, Callable

from .models import WorkflowDefinition, WorkflowEdge, WorkflowNode

logger = logging.getLogger("flint.workflow")


class Node:
    """A single step in a workflow DAG.

    Args:
        id: Unique node identifier within the workflow.
        agent: A FlintAdapter instance (e.g. ``FlintOpenAIAgent``) or a string agent type.
        prompt: The prompt template sent to the agent.
              Use ``{node_id}`` to inject upstream output (auto-injected if omitted).
    """

    def __init__(self, id: str, agent: Any, prompt: str) -> None:
        self._id = id
        self._prompt = prompt
        self._dependencies: list[str] = []
        self._max_retries: int = 3
        self._dead_letter: bool = True
        self._human_approval: bool = False
        self._metadata: dict[str, Any] = {}
        self._adapter: Any = None

        if isinstance(agent, str):
            self._agent = agent
        else:
            self._adapter = agent
            self._agent = agent.get_agent_name()
            if hasattr(agent, "config"):
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
        """Convert to the Pydantic ``WorkflowNode`` model (for C# server compat)."""
        return WorkflowNode(
            Id=self._id,
            AgentType=self._agent,
            PromptTemplate=self._prompt,
            MaxRetries=self._max_retries,
            DeadLetterOnFailure=self._dead_letter,
            HumanApproval=self._human_approval,
        )

    def _to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for the Python server API."""
        d: dict[str, Any] = {
            "id": self._id,
            "agent_type": self._agent,
            "prompt_template": self._prompt,
            "human_approval": self._human_approval,
        }
        if self._max_retries != 3:
            d["retry_policy"] = {"max_retries": self._max_retries}
        if self._metadata:
            d["metadata"] = self._metadata
        return d

    @property
    def adapter(self) -> Any:
        """Return the FlintAdapter instance, if one was provided."""
        return self._adapter

    def __repr__(self) -> str:
        deps = f", depends_on={self._dependencies!r}" if self._dependencies else ""
        return f"Node({self._id!r}, agent={self._agent!r}{deps})"


class Workflow:
    """Fluent builder that assembles and runs a workflow DAG.

    Usage::

        results = (
            Workflow("my-pipeline")
            .add(Node("a", agent=my_agent, prompt="Do X"))
            .add(Node("b", agent=my_agent, prompt="Do Y").depends_on("a"))
            .run()
        )
        print(results["a"])
        print(results["b"])
    """

    def __init__(self, id: str) -> None:
        self._id = id
        self._nodes: list[Node] = []

    # -- chaining helpers ----------------------------------------------------

    def add(self, node: Node) -> Workflow:
        """Append a :class:`Node` to the workflow (returns *self* for chaining)."""
        self._nodes.append(node)
        return self

    # -- validation ----------------------------------------------------------

    def _validate(self) -> None:
        """Check for duplicate IDs, dangling references, and cycles."""
        node_ids: set[str] = set()

        for node in self._nodes:
            if node._id in node_ids:
                raise ValueError(f"Duplicate node id: {node._id!r}")
            node_ids.add(node._id)

        for node in self._nodes:
            for dep in node._dependencies:
                if dep not in node_ids:
                    raise ValueError(f"Node {node._id!r} depends on {dep!r} which does not exist")

        # Cycle detection (Kahn's algorithm)
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
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
        """Validate and return a :class:`WorkflowDefinition` (C# server format)."""
        self._validate()

        wf_nodes = [n._to_workflow_node() for n in self._nodes]
        wf_edges: list[WorkflowEdge] = []
        for node in self._nodes:
            for dep in node._dependencies:
                wf_edges.append(WorkflowEdge(FromNodeId=dep, ToNodeId=node._id))

        return WorkflowDefinition(Id=self._id, Nodes=wf_nodes, Edges=wf_edges)

    def _to_server_dict(self) -> dict[str, Any]:
        """Build a plain dict for the Python server API (snake_case)."""
        self._validate()
        return {
            "id": self._id,
            "name": self._id,
            "nodes": [n._to_dict() for n in self._nodes],
            "edges": [
                {"from_node_id": dep, "to_node_id": node._id} for node in self._nodes for dep in node._dependencies
            ],
        }

    # -- serialisation helpers -----------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Build and serialise to a plain dict (alias-keyed for the API)."""
        return self.build().model_dump(by_alias=True)

    def to_json(self, *, indent: int | None = 2) -> str:
        """Build and serialise to a JSON string (alias-keyed for the API)."""
        return json.dumps(self.to_dict(), indent=indent)

    def __repr__(self) -> str:
        node_ids = [n._id for n in self._nodes]
        return f"Workflow({self._id!r}, nodes={node_ids!r})"

    # ========================================================================
    # run — the whole point
    # ========================================================================

    def run(
        self,
        *,
        server_url: str | None = None,
        port: int = 5160,
        workers: int = 4,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
        verbose: bool = True,
        on_approval: Callable[[str, str], bool] | None = None,
    ) -> dict[str, str]:
        """Run the workflow end-to-end and return results.

        Two modes:
          - **Embedded** (default): starts a Flint engine inside your process.
          - **Remote**: connects to a running Flint server when ``server_url``
            is provided (or ``FLINT_SERVER_URL`` env var is set).

        Args:
            server_url: URL of a running Flint server (e.g. ``http://localhost:5156``).
                If set, the workflow is submitted to that server instead of
                starting an embedded engine.  Also reads ``FLINT_SERVER_URL``
                env var as a fallback.
            port: HTTP port for the embedded engine (default 5160).
            workers: Number of concurrent workers (default 4).
            poll_interval: Seconds between status polls (default 1).
            timeout: Maximum seconds to wait (default 300).
            verbose: Print progress to stdout (default True).
            on_approval: Callback for human-approval nodes. Receives
                ``(node_id, upstream_output)`` and returns ``True`` to
                approve, ``False`` to reject. If ``None``, auto-approves.

        Returns:
            Dict mapping node_id → output string for each completed node.

        Raises:
            RuntimeError: If any node fails or the workflow times out.
        """
        url = server_url or os.environ.get("FLINT_SERVER_URL")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if url:
            # Remote mode — connect to external server
            kwargs = dict(
                server_url=url,
                poll_interval=poll_interval,
                timeout=timeout,
                verbose=verbose,
                on_approval=on_approval,
            )
        else:
            # Embedded mode — start engine in-process
            kwargs = dict(
                port=port,
                workers=workers,
                poll_interval=poll_interval,
                timeout=timeout,
                verbose=verbose,
                on_approval=on_approval,
            )

        coro = self._run_remote(**kwargs) if url else self._run_embedded(**kwargs)

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)

    async def _run_embedded(
        self,
        *,
        port: int = 5160,
        workers: int = 4,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
        verbose: bool = True,
        on_approval: Callable[[str, str], bool] | None = None,
    ) -> dict[str, str]:
        """Internal: start engine, run workflow, collect results, stop engine."""
        import httpx

        from flint_ai.server import FlintEngine, ServerConfig
        from flint_ai.server.config import WorkerConfig

        self._validate()

        def _print(*args: Any, **kw: Any) -> None:
            if verbose:
                print(*args, **kw)

        # ── 1. Start embedded engine ───────────────────────────────────────
        config = ServerConfig(port=port, worker=WorkerConfig(count=workers))
        engine = FlintEngine(config)

        # Register adapters from nodes
        seen_agents: set[str] = set()
        for node in self._nodes:
            if node._adapter and node._agent not in seen_agents:
                engine.register_adapter(node._adapter)
                seen_agents.add(node._agent)

        engine.start()
        base = engine.url

        _print(f"🔥 Flint — running workflow '{self._id}' ({len(self._nodes)} nodes)")
        _print(f"   Dashboard → {base}/ui/\n")

        try:
            async with httpx.AsyncClient(base_url=base, timeout=30) as client:
                # ── 2. Deploy workflow ─────────────────────────────────────
                wf_dict = self._to_server_dict()
                r = await client.post("/workflows", json=wf_dict)
                r.raise_for_status()

                # ── 3. Start run ───────────────────────────────────────────
                r = await client.post(f"/workflows/{self._id}/start")
                r.raise_for_status()
                run_id = r.json()["id"]

                # ── 4. Poll until complete ─────────────────────────────────
                results: dict[str, str] = {}
                last_states: dict[str, str] = {}
                t0 = time.time()

                while True:
                    elapsed = time.time() - t0
                    if elapsed > timeout:
                        pending = [n._id for n in self._nodes if n._id not in results]
                        raise RuntimeError(f"Workflow timed out after {timeout:.0f}s. Pending: {pending}")

                    r = await client.get(f"/workflows/runs/{run_id}")
                    run = r.json()
                    state = run["state"]
                    node_states = run.get("node_states", {})
                    task_ids = run.get("task_ids", {})

                    # Print state changes
                    for nid, nstate in node_states.items():
                        if nid not in last_states or last_states[nid] != nstate:
                            symbol = {
                                "queued": "⏳",
                                "running": "🔄",
                                "succeeded": "✅",
                                "failed": "❌",
                                "pending": "🔒",
                                "dead_letter": "💀",
                            }.get(nstate, "?")
                            _print(f"  {symbol} {nid}")
                            last_states[nid] = nstate

                    # Handle human-approval nodes
                    for node in self._nodes:
                        if node._human_approval and node_states.get(node._id) == "pending" and node._id not in results:
                            # Check if upstream is done
                            upstream_done = all(node_states.get(d) == "succeeded" for d in node._dependencies)
                            if upstream_done:
                                approve = True
                                if on_approval:
                                    # Gather upstream output for the callback
                                    upstream_output = ""
                                    for dep in node._dependencies:
                                        tid = task_ids.get(dep)
                                        if tid:
                                            tr = await client.get(f"/tasks/{tid}")
                                            upstream_output += tr.json().get("result_json", "") + "\n"
                                    approve = on_approval(node._id, upstream_output)

                                if approve:
                                    await client.post(f"/workflows/runs/{run_id}/nodes/{node._id}/approve")
                                    _print(f"  ✅ {node._id} (approved)")
                                else:
                                    await client.post(f"/workflows/runs/{run_id}/nodes/{node._id}/reject")
                                    _print(f"  ❌ {node._id} (rejected)")

                    # Done?
                    if state == "succeeded":
                        break
                    if state == "failed":
                        raise RuntimeError(f"Workflow failed. Node states: {node_states}")

                    await asyncio.sleep(poll_interval)

                # ── 5. Collect results ─────────────────────────────────────
                for node in self._nodes:
                    tid = task_ids.get(node._id)
                    if tid:
                        tr = await client.get(f"/tasks/{tid}")
                        results[node._id] = tr.json().get("result_json", "")

                elapsed = time.time() - t0
                _print(f"\n✅ Done in {elapsed:.0f}s — {len(results)} nodes completed")

                return results
        finally:
            engine.stop()

    async def _run_remote(
        self,
        *,
        server_url: str,
        poll_interval: float = 1.0,
        timeout: float = 300.0,
        verbose: bool = True,
        on_approval: Callable[[str, str], bool] | None = None,
    ) -> dict[str, str]:
        """Submit workflow to a running Flint server, execute tasks locally via FlintWorker."""
        import httpx

        from flint_ai.worker import FlintWorker

        self._validate()

        def _print(*args: Any, **kw: Any) -> None:
            if verbose:
                print(*args, **kw)

        base = server_url.rstrip("/")
        _print(f"🔥 Flint — submitting workflow '{self._id}' to {base}")
        _print(f"   Dashboard → {base}/ui/\n")

        # ── 1. Start FlintWorker with registered adapters ──────────────
        worker = FlintWorker(base)
        seen_agents: set[str] = set()
        for node in self._nodes:
            if node._adapter and node._agent not in seen_agents:
                worker.register(node._agent, node._adapter)
                seen_agents.add(node._agent)

        # Start worker in background (non-blocking)
        worker_task = asyncio.create_task(worker.start_async(poll_interval=poll_interval, concurrency=len(self._nodes)))

        try:
            async with httpx.AsyncClient(base_url=base, timeout=30) as client:
                # ── 2. Deploy workflow ─────────────────────────────────
                wf_dict = self._to_server_dict()
                r = await client.post("/workflows", json=wf_dict)
                r.raise_for_status()

                # ── 3. Start run ───────────────────────────────────────
                r = await client.post(f"/workflows/{self._id}/start")
                r.raise_for_status()
                run_id = r.json()["id"]

                # ── 4. Poll until complete ─────────────────────────────
                results: dict[str, str] = {}
                last_states: dict[str, str] = {}
                t0 = time.time()

                while True:
                    elapsed = time.time() - t0
                    if elapsed > timeout:
                        pending = [n._id for n in self._nodes if n._id not in results]
                        raise RuntimeError(f"Workflow timed out after {timeout:.0f}s. Pending: {pending}")

                    r = await client.get(f"/workflows/runs/{run_id}")
                    run = r.json()
                    state = run["state"]
                    node_states = run.get("node_states", {})
                    task_ids = run.get("task_ids", {})

                    # Print state changes
                    for nid, nstate in node_states.items():
                        if nid not in last_states or last_states[nid] != nstate:
                            symbol = {
                                "queued": "⏳",
                                "running": "🔄",
                                "succeeded": "✅",
                                "failed": "❌",
                                "pending": "🔒",
                                "dead_letter": "💀",
                            }.get(nstate, "?")
                            _print(f"  {symbol} {nid}")
                            last_states[nid] = nstate

                    # Handle human-approval nodes
                    for node in self._nodes:
                        if node._human_approval and node_states.get(node._id) == "pending" and node._id not in results:
                            upstream_done = all(node_states.get(d) == "succeeded" for d in node._dependencies)
                            if upstream_done:
                                approve = True
                                if on_approval:
                                    upstream_output = ""
                                    for dep in node._dependencies:
                                        tid = task_ids.get(dep)
                                        if tid:
                                            tr = await client.get(f"/tasks/{tid}")
                                            upstream_output += tr.json().get("result_json", "") + "\n"
                                    approve = on_approval(node._id, upstream_output)

                                if approve:
                                    await client.post(f"/workflows/runs/{run_id}/nodes/{node._id}/approve")
                                    _print(f"  ✅ {node._id} (approved)")
                                else:
                                    await client.post(f"/workflows/runs/{run_id}/nodes/{node._id}/reject")
                                    _print(f"  ❌ {node._id} (rejected)")

                    if state == "succeeded":
                        break
                    if state == "failed":
                        raise RuntimeError(f"Workflow failed. Node states: {node_states}")

                    await asyncio.sleep(poll_interval)

                # ── 5. Collect results ─────────────────────────────────
                for node in self._nodes:
                    tid = task_ids.get(node._id)
                    if tid:
                        tr = await client.get(f"/tasks/{tid}")
                        results[node._id] = tr.json().get("result_json", "")

                elapsed = time.time() - t0
                _print(f"\n✅ Done in {elapsed:.0f}s — {len(results)} nodes completed")

                return results
        finally:
            worker.stop()
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task


# Alias for discoverability
WorkflowBuilder = Workflow
