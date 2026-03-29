/**
 * Example: Next.js App Router API routes with the orchestrator.
 *
 * Shows how to wire up task and workflow handlers in Next.js route files.
 *
 * Prerequisites:
 *   npm install next @flintai/sdk
 */

// ─────────────────────────────────────────────────────────────────────────────
// File: app/api/tasks/route.ts
// ─────────────────────────────────────────────────────────────────────────────

import { createTaskHandler } from "@flintai/sdk/adapters/nextjs";

// Single handler for all task operations
export const POST = createTaskHandler({
  baseUrl: process.env.ORCHESTRATOR_URL ?? "http://localhost:5156",
  apiKey: process.env.ORCHESTRATOR_API_KEY,
});

/**
 * Usage:
 *
 * Submit a new task:
 *   POST /api/tasks
 *   Body: { "agentType": "openai", "prompt": "Hello" }
 *   Response: { "id": "task-123" }
 *
 * Get task status:
 *   POST /api/tasks
 *   Body: { "taskId": "task-123" }
 *   Response: { "id": "task-123", "state": "Running", ... }
 *
 * Wait for completion:
 *   POST /api/tasks
 *   Body: { "taskId": "task-123", "wait": true }
 *   Response: { "id": "task-123", "state": "Succeeded", "result": "..." }
 *
 * Stream updates (SSE):
 *   POST /api/tasks
 *   Body: { "taskId": "task-123", "stream": true }
 *   Response: text/event-stream
 */

// ─────────────────────────────────────────────────────────────────────────────
// File: app/api/workflows/route.ts
// ─────────────────────────────────────────────────────────────────────────────

import { createWorkflowHandler } from "@flintai/sdk/adapters/nextjs";

export const { POST: WorkflowPOST, GET: WorkflowGET } = createWorkflowHandler({
  baseUrl: process.env.ORCHESTRATOR_URL ?? "http://localhost:5156",
  apiKey: process.env.ORCHESTRATOR_API_KEY,
});

/**
 * Usage:
 *
 * List workflows:
 *   GET /api/workflows
 *
 * Create a workflow:
 *   POST /api/workflows
 *   Body: {
 *     "action": "create",
 *     "definition": {
 *       "Id": "my-pipeline",
 *       "Nodes": [{ "Id": "step-1", "AgentType": "openai", "PromptTemplate": "..." }],
 *       "Edges": []
 *     }
 *   }
 *
 * Start a workflow:
 *   POST /api/workflows
 *   Body: { "action": "start", "workflowId": "my-pipeline" }
 *
 * Approve a node:
 *   POST /api/workflows
 *   Body: { "action": "approve", "workflowId": "my-pipeline", "nodeId": "step-1" }
 */
