CREATE TABLE IF NOT EXISTS workflow_definitions (
  id TEXT PRIMARY KEY,
  definition TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_node_tasks (
  workflow_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  PRIMARY KEY (workflow_id, node_id)
);
