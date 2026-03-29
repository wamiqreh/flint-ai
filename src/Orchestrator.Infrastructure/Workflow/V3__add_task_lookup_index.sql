-- Index for reverse lookup: task_id → node_id (used by GetNodeIdForTaskAsync)
CREATE INDEX IF NOT EXISTS idx_workflow_node_tasks_task_id
  ON workflow_node_tasks(workflow_id, task_id);
