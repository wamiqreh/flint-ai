# @flintai/sdk

TypeScript SDK for the **Flint** AI agent orchestration API.

Zero runtime dependencies — uses native `fetch` (Node.js 18+, Bun, browsers).

## Installation

```bash
npm install @flintai/sdk
```

## Quick Start

```typescript
import { OrchestratorClient } from "@flintai/sdk";

const client = new OrchestratorClient("http://localhost:5156", {
  apiKey: process.env.ORCHESTRATOR_API_KEY,
});

// Submit a task
const taskId = await client.submitTask("dummy", "Hello world");

// Wait for completion
const result = await client.waitForTask(taskId);
console.log(result.state, result.result);
```

## API Reference

### `OrchestratorClient`

```typescript
new OrchestratorClient(baseUrl?, options?)
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `apiKey` | `string` | — | Sent as `X-API-Key` header |
| `timeout` | `number` | `30000` | Request timeout (ms) |
| `retries` | `number` | `3` | Max retries on transient errors |
| `retryBaseDelay` | `number` | `500` | Base delay for exponential backoff (ms) |

#### Task Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `submitTask(agentType, prompt, metadata?)` | `Promise<string>` | Submit a task, get back the ID |
| `getTask(taskId)` | `Promise<TaskRecord>` | Fetch current task state |
| `waitForTask(taskId, pollInterval?, timeout?)` | `Promise<TaskRecord>` | Poll until terminal state |
| `submitTasks(tasks[])` | `Promise<string[]>` | Batch submit tasks in parallel |

#### Workflow Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `createWorkflow(definition)` | `Promise<void>` | Create a workflow DAG |
| `startWorkflow(workflowId)` | `Promise<void>` | Start workflow execution |
| `listWorkflows()` | `Promise<WorkflowDefinition[]>` | List all workflows |
| `getWorkflowNodes(workflowId)` | `Promise<WorkflowNode[]>` | Get workflow nodes |
| `approveNode(workflowId, nodeId)` | `Promise<void>` | Approve a human-approval node |
| `rejectNode(workflowId, nodeId)` | `Promise<void>` | Reject a human-approval node |

### `WorkflowBuilder`

Fluent builder for `WorkflowDefinition` objects:

```typescript
import { WorkflowBuilder } from "@flintai/sdk";

const workflow = new WorkflowBuilder("my-pipeline")
  .addNode({ id: "gen", agentType: "openai", promptTemplate: "Generate code" })
  .addNode({ id: "test", agentType: "dummy", promptTemplate: "Run tests", humanApproval: true })
  .addEdge("gen", "test")
  .build();

await client.createWorkflow(workflow);
await client.startWorkflow("my-pipeline");
```

### Streaming

#### SSE (Server-Sent Events)

```typescript
import { streamTaskUpdates } from "@flintai/sdk";

for await (const update of streamTaskUpdates("http://localhost:5156", taskId)) {
  console.log(update.state, update.result);
}
```

#### WebSocket

```typescript
import { streamTaskUpdatesWs } from "@flintai/sdk";

for await (const update of streamTaskUpdatesWs("http://localhost:5156", taskId)) {
  console.log(update.state, update.result);
}
```

### Error Handling

```typescript
import {
  TaskNotFoundError,
  RateLimitError,
  AuthenticationError,
  WorkflowValidationError,
  TimeoutError,
} from "@flintai/sdk";

try {
  await client.getTask("nonexistent");
} catch (err) {
  if (err instanceof TaskNotFoundError) {
    console.log(`Task ${err.taskId} not found`);
  } else if (err instanceof RateLimitError) {
    console.log(`Rate limited, retry after ${err.retryAfter}s`);
  } else if (err instanceof AuthenticationError) {
    console.log("Invalid API key");
  }
}
```

### Types

```typescript
import type {
  TaskRecord,
  TaskSubmission,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowEdge,
  AgentResult,
} from "@flintai/sdk";

import { TaskState } from "@flintai/sdk";
// TaskState.Pending | Queued | Running | Succeeded | Failed | DeadLetter
```

## Compatibility

- **Node.js** 18+ (native `fetch`)
- **Bun** (all versions)
- **Browsers** with `fetch` and `ReadableStream` support
