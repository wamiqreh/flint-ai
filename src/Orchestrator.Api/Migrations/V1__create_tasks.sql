-- Migration: create tasks table
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  agent_type TEXT NOT NULL,
  prompt TEXT NOT NULL,
  workflow_id TEXT NULL,
  state TEXT NOT NULL,
  result_json TEXT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

