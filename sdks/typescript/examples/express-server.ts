/**
 * Example: Express server with orchestrator middleware.
 *
 * Mounts the orchestrator routes under /orchestrator, giving you
 * a full REST API for task submission, polling, streaming, and workflows.
 *
 * Prerequisites:
 *   npm install express @flintai/sdk
 *
 * Endpoints created:
 *   POST   /orchestrator/tasks              – Submit a task
 *   GET    /orchestrator/tasks/:id          – Get task status
 *   POST   /orchestrator/tasks/:id/wait     – Wait for task completion
 *   GET    /orchestrator/tasks/:id/stream   – SSE stream of task updates
 *   POST   /orchestrator/workflows          – Create a workflow
 *   GET    /orchestrator/workflows          – List workflows
 *   POST   /orchestrator/workflows/:id/start – Start a workflow
 */

import express from "express";
import { createOrchestratorMiddleware } from "@flintai/sdk/adapters/express";

const app = express();
app.use(express.json());

const middleware = createOrchestratorMiddleware({
  baseUrl: "http://localhost:5156",
  apiKey: "your-api-key",
});

// Mount all orchestrator routes under /orchestrator
app.use("/orchestrator", middleware);

// Your own routes
app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.listen(3000, () => {
  console.log("Server listening on http://localhost:3000");
  console.log("Orchestrator routes at http://localhost:3000/orchestrator/");
  console.log("");
  console.log("Try:");
  console.log(
    '  curl -X POST http://localhost:3000/orchestrator/tasks -H "Content-Type: application/json" -d \'{"agentType":"openai","prompt":"Hello"}\'',
  );
});
