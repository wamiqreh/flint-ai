# Skill: DAG Engine Development

Load when: modifying DAG execution, workflow engine, fan-out/fan-in, cycle detection, crash recovery.

## Core File

`flint_ai/server/dag/engine.py` — `DAGEngine` class (600+ lines).

## DAG Structure

```python
class DAG:
    nodes: dict[str, WorkflowNode]   # node_id → node
    edges: list[Edge]                # connections between nodes

class Edge:
    source: str          # source node ID
    target: str          # target node ID
    condition: Condition | None   # optional conditional
    map_variable: str | None      # for dynamic fan-out
```

## Execution Flow

```
start_workflow(definition)
  → validate() — check duplicates, invalid refs, cycles
  → _expand_sub_dags() — inline sub-workflows (max depth 10)
  → create WorkflowRun — all nodes PENDING
  → caller enqueues root nodes

on_task_completed(task_id, result)
  → context.push_result(node_id, result)
  → node.state = SUCCEEDED
  → for each downstream edge:
      → evaluate condition
      → check ALL upstream deps succeeded (fan-in)
      → handle task mapping (fan-out if map_variable)
      → enqueue ready nodes
  → _check_workflow_completion()

on_task_failed(task_id, error)
  → check DAG-level retries → re-submit with backoff
  → check failure-conditional edges → trigger fallback nodes
  → _cascade_failure() → mark all downstream PENDING as CANCELLED
  → _check_workflow_completion()
```

## Key Algorithms

### Cycle Detection — Kahn's Algorithm
```python
def _has_cycle(self) -> bool:
    in_degree = {node: 0 for node in self.nodes}
    for edge in self.edges:
        in_degree[edge.target] += 1
    queue = [n for n, d in in_degree.items() if d == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for edge in self.edges:
            if edge.source == node:
                in_degree[edge.target] -= 1
                if in_degree[edge.target] == 0:
                    queue.append(edge.target)
    return visited != len(self.nodes)
```

### Fan-In
A node becomes ready only when ALL upstream dependencies have `TaskState.SUCCEEDED`:
```python
upstream_states = [self.run.node_states[uid] for uid in upstream_ids]
if all(s == TaskState.SUCCEEDED for s in upstream_states):
    # Node is ready
```

### Fan-Out (Task Mapping)
If `map_variable` is set and context value is a list:
```python
values = context.pull_result(node.map_variable)
for i, value in enumerate(values):
    mapped_id = f"{node_id}__map_{i}"
    # Create mapped node instance with value as input
```

### Failure Cascade
BFS marks all downstream PENDING nodes as CANCELLED:
```python
def _cascade_failure(self, failed_node_id: str):
    queue = [failed_node_id]
    visited = set()
    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        for edge in self.get_downstream_edges(node_id):
            target = edge.target
            if self.run.node_states[target] == TaskState.PENDING:
                self.run.node_states[target] = TaskState.CANCELLED
                queue.append(target)
```

### Crash Recovery
```python
recover_run(run_id):
  → find stale RUNNING workflows
  → for each node:
      SUCCEEDED but downstream not started → re-enqueue downstream
      RUNNING → check if task actually alive
  → re-sync states
```

## Sub-DAG Expansion

Sub-workflow nodes are inlined into parent DAG:
- Node IDs: `{parent}__{sub_node}`
- Incoming edges → redirected to sub-DAG roots
- Outgoing edges → redirected from sub-DAG leaves
- Max recursion depth: 10

## Conditional Edges

`flint_ai/server/dag/conditions.py`

```python
class Condition:
    on_status: list[str] | None   # ["SUCCEEDED", "FAILED"]
    expression: str | None        # Python expression (safe eval)
```

Safe eval uses restricted builtins. Available vars: `result`, `metadata`, `status`, `context`.

## WorkflowContext (Data Passing)

`flint_ai/server/dag/context.py`

```python
context.push_result("research", {"findings": [...]})
context.pull_result("research")  # {"findings": [...]}

# Enriched prompt building
context.build_enriched_prompt("write", upstream_outputs={
    "research": {"findings": [...]}
})
# → If prompt has "{research}" template var → replaces it
# → If no template vars → prepends upstream outputs to prompt
```

## Important Files

| File | Purpose |
|------|---------|
| `flint_ai/server/dag/engine.py` | Main DAG engine |
| `flint_ai/server/dag/context.py` | XCom-style data passing |
| `flint_ai/server/dag/conditions.py` | Conditional edge evaluation |
| `flint_ai/server/dag/scheduler.py` | Cron/interval scheduling |
| `flint_ai/server/engine/__init__.py` | WorkflowNode, RetryPolicy models |

## Testing

`tests/test_server.py` — DAG engine tests
`tests/test_e2e.py` — Workflow DAG execution

```python
async def test_dag_fan_out_fan_in(engine_stack):
    dag = DAG(
        nodes={...},
        edges=[
            Edge("research", "blog"),
            Edge("research", "tweet"),
            Edge("research", "email"),
            Edge("blog", "review"),
            Edge("tweet", "review"),
            Edge("email", "review"),
        ]
    )
    # research → [blog, tweet, email] → review
```

## Gotchas

- Do NOT modify node states directly — use engine methods
- Sub-DAG expansion happens at `start_workflow`, not at definition time
- Task mapping creates NEW node instances — they don't exist in original definition
- Failure cascade is BFS — order matters for cleanup
- `_check_workflow_completion` runs after EVERY task event — keep it fast
