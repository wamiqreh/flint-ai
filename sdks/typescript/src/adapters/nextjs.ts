/**
 * Next.js App Router helpers for Flint.
 *
 * Creates route handlers compatible with the Next.js `app/api/` convention.
 * Uses the Web standard `Request` / `Response` APIs (no Next.js imports needed).
 *
 * ```ts
 * // app/api/tasks/route.ts
 * import { createTaskHandler } from '@flintai/sdk/adapters/nextjs';
 * export const POST = createTaskHandler({ baseUrl: 'http://localhost:5156' });
 *
 * // app/api/workflows/route.ts
 * export const { POST, GET } = createWorkflowHandler({ baseUrl: '...' });
 * ```
 */

import { OrchestratorClient } from "../client.js";
import { streamTaskUpdates } from "../streaming.js";
import { OrchestratorError } from "../errors.js";
import type { OrchestratorClientOptions } from "../types.js";

// ── Types ───────────────────────────────────────────────────────────────────

export interface NextjsAdapterOptions extends OrchestratorClientOptions {
  /** Orchestrator base URL. */
  baseUrl?: string;
  /** Poll interval in ms for waitForTask (default 1000). */
  pollInterval?: number;
  /** Max wait in ms for waitForTask (default 300 000). */
  taskTimeout?: number;
}

/**
 * Next.js App Router handler signature.
 * Compatible with `export const POST = ...` in route.ts files.
 */
type RouteHandler = (
  request: Request,
  context?: { params?: Record<string, string | string[]> },
) => Response | Promise<Response>;

// ── Task handler ────────────────────────────────────────────────────────────

/**
 * Create a Next.js route handler for task operations.
 *
 * Handles:
 * - `POST` with body `{ agentType, prompt, workflowId? }` → submits task, returns `{ id }`
 * - `POST` with body `{ taskId }` → returns task status
 * - `POST` with body `{ taskId, wait: true }` → polls until terminal, returns task
 * - `POST` with body `{ taskId, stream: true }` → SSE stream of updates
 */
export function createTaskHandler(
  options: NextjsAdapterOptions = {},
): RouteHandler {
  const baseUrl = options.baseUrl ?? "http://localhost:5156";
  const pollInterval = options.pollInterval ?? 1_000;
  const taskTimeout = options.taskTimeout ?? 300_000;
  const client = new OrchestratorClient(baseUrl, options);

  return async function taskHandler(request: Request): Promise<Response> {
    try {
      const body = (await request.json()) as Record<string, unknown>;

      // Get task by ID
      if (typeof body.taskId === "string" && !body.agentType) {
        const taskId = body.taskId as string;

        // SSE streaming
        if (body.stream === true) {
          return createSseResponse(baseUrl, taskId, options.apiKey);
        }

        // Wait for terminal state
        if (body.wait === true) {
          const task = await client.waitForTask(taskId, pollInterval, taskTimeout);
          return jsonResponse(task, 200);
        }

        // Simple get
        const task = await client.getTask(taskId);
        return jsonResponse(task, 200);
      }

      // Submit a new task
      if (typeof body.agentType === "string" && typeof body.prompt === "string") {
        const id = await client.submitTask(
          body.agentType as string,
          body.prompt as string,
          { workflowId: body.workflowId as string | undefined },
        );
        return jsonResponse({ id }, 201);
      }

      return jsonResponse(
        { error: "Invalid request body. Provide { agentType, prompt } or { taskId }." },
        400,
      );
    } catch (err) {
      return errorResponse(err);
    }
  };
}

// ── Workflow handler ────────────────────────────────────────────────────────

interface WorkflowHandlers {
  POST: RouteHandler;
  GET: RouteHandler;
}

/**
 * Create Next.js route handlers for workflow operations.
 *
 * - `POST` with body `{ action: 'create', definition: {...} }` → create workflow
 * - `POST` with body `{ action: 'start', workflowId }` → start workflow
 * - `POST` with body `{ action: 'approve', workflowId, nodeId }` → approve node
 * - `POST` with body `{ action: 'reject', workflowId, nodeId }` → reject node
 * - `GET` → list all workflows
 */
export function createWorkflowHandler(
  options: NextjsAdapterOptions = {},
): WorkflowHandlers {
  const baseUrl = options.baseUrl ?? "http://localhost:5156";
  const client = new OrchestratorClient(baseUrl, options);

  const POST: RouteHandler = async (request: Request): Promise<Response> => {
    try {
      const body = (await request.json()) as Record<string, unknown>;
      const action = body.action as string | undefined;

      switch (action) {
        case "create": {
          const definition = body.definition as Parameters<typeof client.createWorkflow>[0];
          if (!definition?.Id || !definition?.Nodes) {
            return jsonResponse(
              { error: "Missing definition.Id and definition.Nodes" },
              400,
            );
          }
          await client.createWorkflow(definition);
          return jsonResponse({ id: definition.Id }, 201);
        }

        case "start": {
          const workflowId = body.workflowId as string | undefined;
          if (!workflowId) {
            return jsonResponse({ error: "Missing workflowId" }, 400);
          }
          await client.startWorkflow(workflowId);
          return jsonResponse({ status: "started" }, 202);
        }

        case "approve": {
          const wid = body.workflowId as string | undefined;
          const nid = body.nodeId as string | undefined;
          if (!wid || !nid) {
            return jsonResponse({ error: "Missing workflowId or nodeId" }, 400);
          }
          await client.approveNode(wid, nid);
          return jsonResponse({ status: "approved" }, 200);
        }

        case "reject": {
          const wid = body.workflowId as string | undefined;
          const nid = body.nodeId as string | undefined;
          if (!wid || !nid) {
            return jsonResponse({ error: "Missing workflowId or nodeId" }, 400);
          }
          await client.rejectNode(wid, nid);
          return jsonResponse({ status: "rejected" }, 200);
        }

        case "nodes": {
          const workflowId = body.workflowId as string | undefined;
          if (!workflowId) {
            return jsonResponse({ error: "Missing workflowId" }, 400);
          }
          const nodes = await client.getWorkflowNodes(workflowId);
          return jsonResponse(nodes, 200);
        }

        default:
          return jsonResponse(
            {
              error:
                "Missing or invalid action. Use: create, start, approve, reject, nodes",
            },
            400,
          );
      }
    } catch (err) {
      return errorResponse(err);
    }
  };

  const GET: RouteHandler = async (): Promise<Response> => {
    try {
      const workflows = await client.listWorkflows();
      return jsonResponse(workflows, 200);
    } catch (err) {
      return errorResponse(err);
    }
  };

  return { POST, GET };
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function errorResponse(err: unknown): Response {
  if (err instanceof OrchestratorError && err.statusCode) {
    return jsonResponse({ error: err.message }, err.statusCode);
  }
  const message = err instanceof Error ? err.message : "Internal server error";
  return jsonResponse({ error: message }, 500);
}

function createSseResponse(
  baseUrl: string,
  taskId: string,
  apiKey?: string,
): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      try {
        for await (const update of streamTaskUpdates(baseUrl, taskId, { apiKey })) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(update)}\n\n`));
        }
      } catch (err) {
        controller.enqueue(
          encoder.encode(
            `event: error\ndata: ${JSON.stringify({ error: String(err) })}\n\n`,
          ),
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
