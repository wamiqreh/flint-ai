CREATE TABLE IF NOT EXISTS workflow_node_attempts (
  workflow_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (workflow_id, node_id)
);
