/**
 * Quick-start example: submit a task, poll until complete, print the result.
 *
 * Usage:
 *   npx tsx examples/basic.ts
 */
import {
  OrchestratorClient,
  WorkflowBuilder,
  streamTaskUpdates,
  TaskState,
} from "../src/index.js";

const BASE_URL = process.env.ORCHESTRATOR_URL ?? "http://localhost:5156";
const API_KEY = process.env.ORCHESTRATOR_API_KEY;

async function main() {
  const client = new OrchestratorClient(BASE_URL, {
    apiKey: API_KEY,
    timeout: 10_000,
    retries: 2,
  });

  // ── 1. Submit a single task ────────────────────────────────────────────
  console.log("Submitting task…");
  const taskId = await client.submitTask("dummy", "Hello from the TypeScript SDK!");
  console.log(`  Task created: ${taskId}`);

  // ── 2. Poll until the task finishes ────────────────────────────────────
  console.log("Waiting for task to complete…");
  const result = await client.waitForTask(taskId, 1_000, 60_000);
  console.log(`  Final state : ${result.state}`);
  console.log(`  Result      : ${result.result ?? "(none)"}`);

  // ── 3. Batch submit ────────────────────────────────────────────────────
  console.log("\nSubmitting batch of tasks…");
  const ids = await client.submitTasks([
    { agentType: "dummy", prompt: "Task A" },
    { agentType: "dummy", prompt: "Task B" },
    { agentType: "dummy", prompt: "Task C" },
  ]);
  console.log(`  Created ${ids.length} tasks: ${ids.join(", ")}`);

  // ── 4. Stream updates via SSE ──────────────────────────────────────────
  console.log("\nStreaming updates for first batch task…");
  for await (const update of streamTaskUpdates(BASE_URL, ids[0], { apiKey: API_KEY })) {
    console.log(`  [stream] state=${update.state}`);
    if (
      update.state === TaskState.Succeeded ||
      update.state === TaskState.Failed ||
      update.state === TaskState.DeadLetter
    ) {
      break;
    }
  }

  // ── 5. Create & start a workflow ───────────────────────────────────────
  console.log("\nCreating workflow…");
  const workflow = new WorkflowBuilder("ts-sdk-demo")
    .addNode({
      id: "generate",
      agentType: "dummy",
      promptTemplate: "Generate code for a hello-world app",
    })
    .addNode({
      id: "test",
      agentType: "dummy",
      promptTemplate: "Run unit tests",
      humanApproval: true,
    })
    .addEdge("generate", "test")
    .build();

  await client.createWorkflow(workflow);
  console.log(`  Workflow "${workflow.Id}" created`);

  await client.startWorkflow(workflow.Id);
  console.log(`  Workflow "${workflow.Id}" started`);

  const nodes = await client.getWorkflowNodes(workflow.Id);
  console.log(`  Nodes: ${nodes.map((n) => n.Id).join(", ")}`);

  console.log("\nDone ✓");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
