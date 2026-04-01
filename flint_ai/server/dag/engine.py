"""DAG execution engine — orchestrates workflow runs.

Handles:
- Topological sort and dependency resolution
- Sub-DAG expansion
- Task mapping (fan-out)
- Conditional edge evaluation
- XCom-style data passing
- Human approval gates
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from flint_ai.server.dag.conditions import evaluate_condition
from flint_ai.server.dag.context import WorkflowContext
from flint_ai.server.engine import (
    TaskRecord,
    TaskState,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowRun,
    WorkflowRunState,
)
from flint_ai.server.store import BaseTaskStore, BaseWorkflowStore

logger = logging.getLogger("flint.server.dag.engine")


class DAGValidationError(Exception):
    """Raised when a DAG definition is invalid."""


class DAGEngine:
    """Manages DAG workflow execution."""

    def __init__(
        self,
        workflow_store: BaseWorkflowStore,
        task_store: BaseTaskStore,
    ) -> None:
        self._wf_store = workflow_store
        self._task_store = task_store

    # ------------------------------------------------------------------
    # DAG Validation
    # ------------------------------------------------------------------

    def validate(self, definition: WorkflowDefinition) -> List[str]:
        """Validate a workflow definition. Returns list of errors (empty = valid)."""
        errors: List[str] = []
        node_ids = {n.id for n in definition.nodes}

        # Check for duplicate node IDs
        seen: Set[str] = set()
        for node in definition.nodes:
            if node.id in seen:
                errors.append(f"Duplicate node ID: {node.id}")
            seen.add(node.id)

        # Check edges reference valid nodes
        for edge in definition.edges:
            if edge.from_node_id not in node_ids:
                errors.append(f"Edge references unknown source node: {edge.from_node_id}")
            if edge.to_node_id not in node_ids:
                errors.append(f"Edge references unknown target node: {edge.to_node_id}")

        # Check for cycles (Kahn's algorithm)
        if not errors:
            if self._has_cycle(definition.nodes, definition.edges):
                errors.append("Workflow contains a cycle")

        # Check sub-workflow references exist (deferred — can't validate at definition time)
        for node in definition.nodes:
            if node.sub_workflow_id and node.sub_workflow_id == definition.id:
                errors.append(f"Node {node.id} references its own workflow as sub-workflow")

        return errors

    def _has_cycle(self, nodes: List[WorkflowNode], edges: List[WorkflowEdge]) -> bool:
        """Detect cycles using Kahn's topological sort algorithm."""
        in_degree: Dict[str, int] = {n.id: 0 for n in nodes}
        adj: Dict[str, List[str]] = defaultdict(list)

        for edge in edges:
            adj[edge.from_node_id].append(edge.to_node_id)
            in_degree[edge.to_node_id] = in_degree.get(edge.to_node_id, 0) + 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited = 0

        while queue:
            node = queue.popleft()
            visited += 1
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited != len(nodes)

    def topological_sort(self, definition: WorkflowDefinition) -> List[str]:
        """Return node IDs in topological order."""
        in_degree: Dict[str, int] = {n.id: 0 for n in definition.nodes}
        adj: Dict[str, List[str]] = defaultdict(list)

        for edge in definition.edges:
            adj[edge.from_node_id].append(edge.to_node_id)
            in_degree[edge.to_node_id] = in_degree.get(edge.to_node_id, 0) + 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: List[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result

    def get_root_nodes(self, definition: WorkflowDefinition) -> List[WorkflowNode]:
        """Get nodes with no incoming edges (DAG roots)."""
        targets = {e.to_node_id for e in definition.edges}
        return [n for n in definition.nodes if n.id not in targets]

    def get_upstream_nodes(
        self, node_id: str, definition: WorkflowDefinition
    ) -> List[str]:
        """Get all direct predecessor node IDs."""
        return [e.from_node_id for e in definition.edges if e.to_node_id == node_id]

    def get_downstream_edges(
        self, node_id: str, definition: WorkflowDefinition
    ) -> List[WorkflowEdge]:
        """Get all outgoing edges from a node."""
        return [e for e in definition.edges if e.from_node_id == node_id]

    def get_ready_nodes(
        self, definition: WorkflowDefinition, run: WorkflowRun
    ) -> List[WorkflowNode]:
        """Get nodes whose all upstream dependencies have succeeded.

        A node is "ready" if:
        - All its upstream nodes have succeeded
        - It hasn't been started yet (state is pending or not set)
        """
        ready = []
        for node in definition.nodes:
            current = run.node_states.get(node.id)
            # Skip already-started nodes
            current_val = current.value if hasattr(current, 'value') else str(current) if current else None
            if current_val and current_val not in ("pending",):
                continue

            # Check all upstream nodes
            upstream_ids = self.get_upstream_nodes(node.id, definition)
            if not upstream_ids:
                continue  # root nodes are handled at start time

            all_done = all(
                self._node_succeeded(run.node_states.get(uid))
                for uid in upstream_ids
            )
            if all_done:
                ready.append(node)
        return ready

    @staticmethod
    def _node_succeeded(state) -> bool:
        if state is None:
            return False
        val = state.value if hasattr(state, 'value') else str(state)
        return val == "succeeded"

    def get_node(self, node_id: str, definition: WorkflowDefinition) -> Optional[WorkflowNode]:
        """Get a node by ID."""
        for n in definition.nodes:
            if n.id == node_id:
                return n
        return None

    # ------------------------------------------------------------------
    # Workflow execution
    # ------------------------------------------------------------------

    async def start_workflow(
        self,
        workflow_id: str,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowRun:
        """Start a new workflow run by enqueuing root nodes."""
        definition = await self._wf_store.get_definition(workflow_id)
        if not definition:
            raise ValueError(f"Workflow {workflow_id} not found")

        errors = self.validate(definition)
        if errors:
            raise DAGValidationError(f"Invalid workflow: {'; '.join(errors)}")

        # Expand sub-DAGs
        definition = await self._expand_sub_dags(definition)

        run = WorkflowRun(
            workflow_id=workflow_id,
            state=WorkflowRunState.RUNNING,
            context=initial_context or {},
        )

        # Initialize node states
        for node in definition.nodes:
            run.node_states[node.id] = TaskState.PENDING
            run.node_task_ids[node.id] = []

        run = await self._wf_store.create_run(run)

        # Return run — root node tasks will be created by the caller (API layer)
        logger.info(
            "Started workflow run=%s for workflow=%s (%d nodes)",
            run.id, workflow_id, len(definition.nodes),
        )
        return run

    async def _expand_sub_dags(
        self, definition: WorkflowDefinition, depth: int = 0
    ) -> WorkflowDefinition:
        """Recursively expand sub-DAG references into the parent workflow."""
        if depth > 10:
            raise DAGValidationError("Sub-DAG recursion depth exceeded (max 10)")

        expanded_nodes: List[WorkflowNode] = []
        expanded_edges: List[WorkflowEdge] = list(definition.edges)
        sub_dag_nodes: Set[str] = set()

        for node in definition.nodes:
            if node.sub_workflow_id:
                sub_def = await self._wf_store.get_definition(node.sub_workflow_id)
                if not sub_def:
                    raise DAGValidationError(
                        f"Sub-workflow {node.sub_workflow_id} not found (referenced by {node.id})"
                    )

                # Recursively expand
                sub_def = await self._expand_sub_dags(sub_def, depth + 1)

                # Prefix sub-DAG node IDs to avoid collisions
                prefix = f"{node.id}__"
                sub_roots = self.get_root_nodes(sub_def)
                sub_leaves = self._get_leaf_nodes(sub_def)

                # Add prefixed sub-nodes
                for sn in sub_def.nodes:
                    new_node = sn.model_copy(update={"id": f"{prefix}{sn.id}"})
                    expanded_nodes.append(new_node)

                # Add prefixed sub-edges
                for se in sub_def.edges:
                    expanded_edges.append(
                        WorkflowEdge(
                            from_node_id=f"{prefix}{se.from_node_id}",
                            to_node_id=f"{prefix}{se.to_node_id}",
                            condition=se.condition,
                        )
                    )

                # Redirect incoming edges to sub-DAG roots
                for i, edge in enumerate(expanded_edges):
                    if edge.to_node_id == node.id:
                        for root in sub_roots:
                            expanded_edges.append(
                                WorkflowEdge(
                                    from_node_id=edge.from_node_id,
                                    to_node_id=f"{prefix}{root.id}",
                                    condition=edge.condition,
                                )
                            )

                # Redirect outgoing edges from sub-DAG leaves
                for i, edge in enumerate(expanded_edges):
                    if edge.from_node_id == node.id:
                        for leaf in sub_leaves:
                            expanded_edges.append(
                                WorkflowEdge(
                                    from_node_id=f"{prefix}{leaf.id}",
                                    to_node_id=edge.to_node_id,
                                    condition=edge.condition,
                                )
                            )

                sub_dag_nodes.add(node.id)
            else:
                expanded_nodes.append(node)

        # Remove edges that reference the original sub-DAG placeholder node
        expanded_edges = [
            e for e in expanded_edges
            if e.from_node_id not in sub_dag_nodes and e.to_node_id not in sub_dag_nodes
        ]

        return definition.model_copy(
            update={"nodes": expanded_nodes, "edges": expanded_edges}
        )

    def _get_leaf_nodes(self, definition: WorkflowDefinition) -> List[WorkflowNode]:
        """Get nodes with no outgoing edges."""
        sources = {e.from_node_id for e in definition.edges}
        return [n for n in definition.nodes if n.id not in sources]

    # ------------------------------------------------------------------
    # Task completion handling
    # ------------------------------------------------------------------

    async def on_task_completed(
        self,
        run: WorkflowRun,
        node_id: str,
        task_record: TaskRecord,
        definition: WorkflowDefinition,
    ) -> List[Tuple[WorkflowNode, str]]:
        """Handle a task completion within a workflow.

        Updates node state, evaluates downstream conditions, and returns
        a list of (node, enriched_prompt) tuples that should be enqueued.

        Returns:
            List of (WorkflowNode, enriched_prompt) for nodes ready to execute.
        """
        context = WorkflowContext.from_dict(run.context)

        # Store result in context (XCom-style)
        context.push_result(
            node_id,
            task_record.result_json or "",
            task_record.metadata,
        )

        # Update node state
        run.node_states[node_id] = task_record.state
        run.context = context.to_dict()
        await self._wf_store.update_run(run)

        ready_nodes: List[Tuple[WorkflowNode, str]] = []

        if task_record.state == TaskState.SUCCEEDED:
            # Find downstream nodes
            downstream_edges = self.get_downstream_edges(node_id, definition)

            for edge in downstream_edges:
                # Evaluate edge condition
                should_fire = evaluate_condition(
                    edge.condition,
                    task_record.state,
                    task_record.result_json,
                    task_record.metadata,
                    run.context,
                )

                if not should_fire:
                    logger.debug(
                        "Edge %s→%s condition not met, skipping",
                        edge.from_node_id, edge.to_node_id,
                    )
                    continue

                # Check if ALL upstream dependencies of the target node are satisfied
                target_node = self.get_node(edge.to_node_id, definition)
                if not target_node:
                    continue

                upstream_ids = self.get_upstream_nodes(edge.to_node_id, definition)
                all_ready = all(
                    run.node_states.get(uid) == TaskState.SUCCEEDED
                    for uid in upstream_ids
                )

                if all_ready:
                    # Build enriched prompt with upstream outputs
                    enriched = context.build_enriched_prompt(
                        target_node.prompt_template, upstream_ids
                    )

                    # Handle task mapping (fan-out)
                    if target_node.map_variable:
                        map_data = context.pull(node_id, target_node.map_variable)
                        if isinstance(map_data, list):
                            for i, item in enumerate(map_data):
                                mapped_prompt = f"{enriched}\n\n[Map item {i}]: {item}"
                                mapped_node = target_node.model_copy(
                                    update={"id": f"{target_node.id}__map_{i}"}
                                )
                                ready_nodes.append((mapped_node, mapped_prompt))
                        else:
                            ready_nodes.append((target_node, enriched))
                    else:
                        ready_nodes.append((target_node, enriched))

        # Check if workflow is complete
        await self._check_workflow_completion(run, definition)

        return ready_nodes

    async def on_task_failed(
        self,
        run: WorkflowRun,
        node_id: str,
        task_record: TaskRecord,
        definition: WorkflowDefinition,
    ) -> Optional[Tuple[WorkflowNode, str]]:
        """Handle a task failure. Returns (node, prompt) if retry should happen."""
        # Update node state first
        run.node_states[node_id] = task_record.state

        node = self.get_node(node_id, definition)
        if not node:
            await self._cascade_failure(run, node_id, definition)
            await self._check_workflow_completion(run, definition)
            return None

        attempt = len(run.node_task_ids.get(node_id, []))

        if attempt < node.retry_policy.max_retries:
            # Retry: return the node with original prompt
            delay = node.retry_policy.delay_for_attempt(attempt)
            logger.info(
                "Node %s retry %d/%d (delay=%.1fs)",
                node_id, attempt + 1, node.retry_policy.max_retries, delay,
            )
            run.node_states[node_id] = TaskState.QUEUED
            await self._wf_store.update_run(run)
            return (node, task_record.prompt)
        else:
            # Exhausted retries
            if node.dead_letter_on_failure:
                run.node_states[node_id] = TaskState.DEAD_LETTER
            else:
                run.node_states[node_id] = TaskState.FAILED
            await self._wf_store.update_run(run)

            # Check downstream edges for failure-conditional edges
            downstream_edges = self.get_downstream_edges(node_id, definition)
            for edge in downstream_edges:
                if edge.condition.on_status and TaskState.FAILED in edge.condition.on_status:
                    target = self.get_node(edge.to_node_id, definition)
                    if target:
                        context = WorkflowContext.from_dict(run.context)
                        upstream_ids = self.get_upstream_nodes(edge.to_node_id, definition)
                        enriched = context.build_enriched_prompt(
                            target.prompt_template, upstream_ids
                        )
                        return (target, enriched)

            # No failure-conditional edges — cascade failure to all downstream
            await self._cascade_failure(run, node_id, definition)
            await self._check_workflow_completion(run, definition)
            return None

    async def _cascade_failure(
        self, run: WorkflowRun, failed_node_id: str, definition: WorkflowDefinition
    ) -> None:
        """Cancel all downstream nodes that can no longer run due to upstream failure."""
        visited: Set[str] = set()
        queue: List[str] = [failed_node_id]

        while queue:
            current = queue.pop(0)
            for edge in self.get_downstream_edges(current, definition):
                child = edge.to_node_id
                if child in visited:
                    continue
                visited.add(child)
                state = run.node_states.get(child)
                state_val = state.value if hasattr(state, 'value') else str(state) if state else None
                if state_val in ("pending", None):
                    run.node_states[child] = TaskState.CANCELLED
                    logger.info("Cascading failure: cancelled node=%s", child)
                    queue.append(child)

        await self._wf_store.update_run(run)

    async def _check_workflow_completion(
        self, run: WorkflowRun, definition: WorkflowDefinition
    ) -> None:
        """Check if all nodes are in terminal states → mark workflow as complete."""
        all_terminal = all(
            TaskState(s).is_terminal if isinstance(s, str) else s.is_terminal
            for s in run.node_states.values()
        )

        if not all_terminal:
            return

        # Determine overall status
        states = list(run.node_states.values())
        if all(
            (s == TaskState.SUCCEEDED if isinstance(s, TaskState) else s == "succeeded")
            for s in states
        ):
            run.state = WorkflowRunState.SUCCEEDED
        else:
            run.state = WorkflowRunState.FAILED

        run.completed_at = datetime.now(timezone.utc)
        await self._wf_store.update_run(run)
        logger.info(
            "Workflow run=%s completed: %s", run.id, run.state.value
        )

    # ------------------------------------------------------------------
    # Approval handling
    # ------------------------------------------------------------------

    async def approve_node(
        self, run: WorkflowRun, node_id: str, definition: WorkflowDefinition
    ) -> Optional[Tuple[WorkflowNode, str]]:
        """Approve a pending human-approval node. Returns (node, prompt) to enqueue."""
        node = self.get_node(node_id, definition)
        if not node:
            return None

        if run.node_states.get(node_id) != TaskState.PENDING:
            return None

        context = WorkflowContext.from_dict(run.context)
        upstream_ids = self.get_upstream_nodes(node_id, definition)
        enriched = context.build_enriched_prompt(node.prompt_template, upstream_ids)

        run.node_states[node_id] = TaskState.QUEUED
        await self._wf_store.update_run(run)

        logger.info("Approved node=%s in run=%s", node_id, run.id)
        return (node, enriched)

    async def reject_node(
        self, run: WorkflowRun, node_id: str, definition: WorkflowDefinition
    ) -> None:
        """Reject a pending human-approval node → dead letter."""
        run.node_states[node_id] = TaskState.DEAD_LETTER
        await self._wf_store.update_run(run)
        await self._check_workflow_completion(run, definition)
        logger.info("Rejected node=%s in run=%s", node_id, run.id)
