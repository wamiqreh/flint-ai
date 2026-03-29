# TypeScript SDK

The official TypeScript/Node.js client for Flint. Fully typed, Promise-based, with built-in streaming support.

---

## Installation

```bash
npm install @flint-ai/sdk
```

```bash
# or with yarn
yarn add @flint-ai/sdk

# or with pnpm
pnpm add @flint-ai/sdk
```

**Requirements:** Node.js 18+ (uses native `fetch`)

---

## Client Setup

```typescript
import { OrchestratorClient } from "@flint-ai/sdk";

const client = new OrchestratorClient({
  baseUrl: "http://localhost:5156", // defaults to this
  timeout: 30_000,                 // request timeout in ms
  maxRetries: 3,                   // retries on 429, 502, 503, 504
});
```

### With API Key

```typescript
const client = new OrchestratorClient({
  baseUrl: "http://localhost:5156",
  apiKey: "your-api-key", // sent as X-API-Key header
});
```

---

## Task Operations

### Submit a Task

```typescript
const taskId = await client.submitTask("openai", "Write a haiku about TypeScript");
console.log(`Task submitted: ${taskId}`);
```

### Get Task Status

```typescript
const task = await client.getTask(taskId);
console.log(task.id);     // "3fa85f64-..."
console.log(task.state);  // "Pending" | "Queued" | "Running" | "Succeeded" | "Failed" | "DeadLetter"
console.log(task.result); // agent output (when succeeded)
```

### Wait for Completion

```typescript
const result = await client.waitForTask(taskId, {
  pollIntervalMs: 1000, // default: 1000ms
});

if (result.state === "Succeeded") {
  console.log(result.result);
} else {
  console.error(`Task failed: ${result.state}`);
}
```

### Batch Submit

```typescript
const taskIds = await client.submitTasks([
  { agentType: "openai", prompt: "Translate to French: Hello" },
  { agentType: "openai", prompt: "Translate to Spanish: Hello" },
  { agentType: "openai", prompt: "Translate to German: Hello" },
]);

// Wait for all in parallel
const results = await Promise.all(
  taskIds.map((id) => client.waitForTask(id))
);
results.forEach((r) => console.log(r.result));
```

---

## Workflow Operations

### Define and Create a Workflow

```typescript
import type { WorkflowDefinition } from "@flint-ai/sdk";

const workflow: WorkflowDefinition = {
  id: "content-pipeline",
  nodes: [
    {
      id: "draft",
      agentType: "openai",
      promptTemplate: "Write a blog post about AI agents",
      maxRetries: 3,
      deadLetterOnFailure: true,
      humanApproval: false,
    },
    {
      id: "review",
      agentType: "openai",
      promptTemplate: "Review this blog post for accuracy",
      humanApproval: true, // pauses for human approval
    },
    {
      id: "publish",
      agentType: "openai",
      promptTemplate: "Format and publish the blog post",
    },
  ],
  edges: [
    { fromNodeId: "draft", toNodeId: "review" },
    { fromNodeId: "review", toNodeId: "publish" },
  ],
};

await client.createWorkflow(workflow);
```

### Start a Workflow

```typescript
await client.startWorkflow("content-pipeline");
```

### List Workflows

```typescript
const workflows = await client.listWorkflows();
workflows.forEach((wf) => {
  console.log(`${wf.id}: ${wf.nodes.length} nodes`);
});
```

### Get Node States

```typescript
const nodes = await client.getWorkflowNodes("content-pipeline");
nodes.forEach((node) => {
  console.log(`  ${node.id}: ${node.state}`);
});
```

---

## Workflow Builder

Build workflows programmatically with a fluent API:

```typescript
import { WorkflowBuilder } from "@flint-ai/sdk";

const workflow = new WorkflowBuilder("data-pipeline")
  .addNode({
    id: "extract",
    agentType: "openai",
    promptTemplate: "Extract key data from the document",
  })
  .addNode({
    id: "transform",
    agentType: "openai",
    promptTemplate: "Clean and normalize the extracted data",
    maxRetries: 5,
  })
  .addNode({
    id: "validate",
    agentType: "openai",
    promptTemplate: "Validate the transformed data",
    humanApproval: true,
  })
  .addEdge("extract", "transform")
  .addEdge("transform", "validate")
  .build();

await client.createWorkflow(workflow);
await client.startWorkflow("data-pipeline");
```

### Linear Pipeline Shortcut

```typescript
// Automatically creates edges between sequential nodes
const pipeline = new WorkflowBuilder("simple-pipeline")
  .addLinearPipeline([
    { id: "step1", agentType: "openai", promptTemplate: "First step" },
    { id: "step2", agentType: "openai", promptTemplate: "Second step" },
    { id: "step3", agentType: "openai", promptTemplate: "Third step" },
  ])
  .build();
```

---

## Streaming

### Server-Sent Events (SSE)

Stream real-time task state changes:

```typescript
const stream = client.streamTask(taskId);

for await (const update of stream) {
  console.log(`State: ${update.state}`);
  if (update.state === "Succeeded") {
    console.log(`Result: ${update.result}`);
    break;
  }
}
```

### WebSocket

For bidirectional communication:

```typescript
const ws = client.connectWebSocket(taskId);

ws.onMessage((update) => {
  console.log(`State: ${update.state}`);
  if (update.state === "Succeeded") {
    console.log(`Result: ${update.result}`);
    ws.close();
  }
});

ws.onError((err) => console.error("WebSocket error:", err));
ws.onClose(() => console.log("Connection closed"));
```

### Raw SSE with EventSource

If you prefer to use the native `EventSource` API directly:

```typescript
const es = new EventSource(
  "http://localhost:5156/tasks/{taskId}/stream"
);

es.addEventListener("message", (event) => {
  const task = JSON.parse(event.data);
  console.log(task.state, task.result);
});

es.addEventListener("error", () => es.close());
```

---

## Error Handling

The SDK throws typed errors:

```typescript
import {
  OrchestratorError,
  TaskNotFoundError,
  RateLimitError,
  WorkflowValidationError,
  AuthenticationError,
  ConnectionError,
} from "@flint-ai/sdk";

try {
  const task = await client.getTask("nonexistent-id");
} catch (err) {
  if (err instanceof TaskNotFoundError) {
    console.log(`Not found (${err.statusCode}): ${err.message}`);
  } else if (err instanceof RateLimitError) {
    console.log(`Rate limited. Retry after ${err.retryAfter}s`);
  } else if (err instanceof AuthenticationError) {
    console.log(`Auth failed: ${err.message}`);
  } else if (err instanceof ConnectionError) {
    console.log(`Server unreachable: ${err.message}`);
  } else if (err instanceof OrchestratorError) {
    console.log(`API error ${err.statusCode}: ${err.detail}`);
  }
}
```

### Error Hierarchy

```
OrchestratorError (base)
├── TaskNotFoundError        (404)
├── WorkflowValidationError  (422)
├── RateLimitError           (429, includes retryAfter)
├── AuthenticationError      (401, 403)
└── ConnectionError          (network failure)
```

### Automatic Retries

The client automatically retries transient errors (429, 502, 503, 504) with exponential backoff and jitter. Configure with:

```typescript
const client = new OrchestratorClient({
  maxRetries: 5,
  retryDelayMs: 500,   // base delay
  maxRetryDelayMs: 30_000, // max delay
});
```

---

## TypeScript Types

All types are fully exported:

```typescript
import type {
  TaskResponse,
  TaskSubmission,
  WorkflowDefinition,
  WorkflowNode,
  WorkflowEdge,
  OrchestratorConfig,
} from "@flint-ai/sdk";
```

### TaskResponse

```typescript
interface TaskResponse {
  id: string;
  state: "Pending" | "Queued" | "Running" | "Succeeded" | "Failed" | "DeadLetter";
  result?: string;
  workflowId?: string;
}
```

### WorkflowNode

```typescript
interface WorkflowNode {
  id: string;
  agentType: string;
  promptTemplate: string;
  maxRetries?: number;           // default: 3
  deadLetterOnFailure?: boolean; // default: true
  humanApproval?: boolean;       // default: false
}
```

### WorkflowEdge

```typescript
interface WorkflowEdge {
  fromNodeId: string;
  toNodeId: string;
  condition?: string;
}
```

---

## Examples

### Express.js Integration

```typescript
import express from "express";
import { OrchestratorClient } from "@flint-ai/sdk";

const app = express();
const client = new OrchestratorClient();

app.post("/summarize", express.json(), async (req, res) => {
  const taskId = await client.submitTask("openai", req.body.text);
  const result = await client.waitForTask(taskId);
  res.json({ summary: result.result });
});

app.listen(3000);
```

### Next.js API Route

```typescript
// app/api/task/route.ts
import { OrchestratorClient } from "@flint-ai/sdk";
import { NextResponse } from "next/server";

const client = new OrchestratorClient({
  baseUrl: process.env.ORCHESTRATOR_URL ?? "http://localhost:5156",
});

export async function POST(request: Request) {
  const { prompt } = await request.json();
  const taskId = await client.submitTask("openai", prompt);
  return NextResponse.json({ taskId });
}
```

### Deno

```typescript
import { OrchestratorClient } from "npm:@flint-ai/sdk";

const client = new OrchestratorClient();
const taskId = await client.submitTask("dummy", "Hello from Deno!");
const result = await client.waitForTask(taskId);
console.log(result.result);
```
