/**
 * Express middleware adapter for Flint.
 *
 * Mounts RESTful routes that proxy to the orchestrator API, so you can
 * expose orchestrator functionality through your own Express server.
 *
 * Zero external dependencies — uses duck-typed Express interfaces.
 *
 * ```ts
 * import { createOrchestratorMiddleware } from '@flintai/sdk/adapters/express';
 * app.use('/orchestrator', createOrchestratorMiddleware({ baseUrl: '...' }));
 * ```
 */

import { OrchestratorClient } from "../client.js";
import { streamTaskUpdates } from "../streaming.js";
import type { OrchestratorClientOptions } from "../types.js";
import { OrchestratorError } from "../errors.js";

// ── Duck-typed Express interfaces ───────────────────────────────────────────

interface Request {
  method: string;
  path: string;
  params: Record<string, string>;
  body?: unknown;
  query?: Record<string, string | string[] | undefined>;
}

interface Response {
  status(code: number): Response;
  json(body: unknown): void;
  setHeader(name: string, value: string): void;
  write(chunk: string): boolean;
  end(): void;
  headersSent: boolean;
  writableEnded?: boolean;
  on?(event: string, listener: () => void): void;
}

type NextFunction = (err?: unknown) => void;
type Middleware = (req: Request, res: Response, next: NextFunction) => void;

interface Router {
  post(path: string, handler: Middleware): void;
  get(path: string, handler: Middleware): void;
  use(...handlers: Middleware[]): void;
}

// ── Options ─────────────────────────────────────────────────────────────────

export interface ExpressAdapterOptions extends OrchestratorClientOptions {
  /** Orchestrator base URL. */
  baseUrl?: string;
  /** Poll interval in ms for the wait endpoint (default 1000). */
  pollInterval?: number;
  /** Max wait in ms for the wait endpoint (default 300 000). */
  taskTimeout?: number;
}

// ── Implementation ──────────────────────────────────────────────────────────

/**
 * Create an Express-compatible Router that proxies to the orchestrator.
 *
 * Mounted routes:
 * - `POST   /tasks`                – Submit a task
 * - `GET    /tasks/:id`            – Get task status
 * - `POST   /tasks/:id/wait`       – Poll until terminal (returns final task)
 * - `GET    /tasks/:id/stream`     – SSE stream of task updates
 * - `POST   /workflows`            – Create a workflow
 * - `GET    /workflows`            – List workflows
 * - `POST   /workflows/:id/start`  – Start a workflow
 * - `GET    /workflows/:id/nodes`  – Get workflow nodes
 * - `POST   /workflows/:wid/nodes/:nid/approve` – Approve node
 * - `POST   /workflows/:wid/nodes/:nid/reject`  – Reject node
 */
export function createOrchestratorMiddleware(
  options: ExpressAdapterOptions = {},
): Middleware {
  const baseUrl = options.baseUrl ?? "http://localhost:5156";
  const pollInterval = options.pollInterval ?? 1_000;
  const taskTimeout = options.taskTimeout ?? 300_000;
  const client = new OrchestratorClient(baseUrl, options);

  // Simple path-based router since we can't depend on Express
  const routes: Array<{
    method: string;
    pattern: RegExp;
    paramNames: string[];
    handler: Middleware;
  }> = [];

  function addRoute(
    method: string,
    path: string,
    handler: (req: Request, res: Response, next: NextFunction) => void | Promise<void>,
  ) {
    const paramNames: string[] = [];
    const pattern = new RegExp(
      "^" +
        path.replace(/:([^/]+)/g, (_match, name) => {
          paramNames.push(name);
          return "([^/]+)";
        }) +
        "$",
    );
    routes.push({
      method: method.toUpperCase(),
      pattern,
      paramNames,
      handler: (req, res, next) => {
        const result = handler(req, res, next);
        if (result && typeof result === "object" && "catch" in result) {
          (result as Promise<void>).catch(next);
        }
      },
    });
  }

  // ── Task routes ─────────────────────────────────────────────────────────

  addRoute("POST", "/tasks", async (req, res) => {
    const body = req.body as { agentType?: string; prompt?: string; workflowId?: string } | undefined;
    if (!body?.agentType || !body?.prompt) {
      res.status(400).json({ error: "Missing required fields: agentType, prompt" });
      return;
    }
    const id = await client.submitTask(body.agentType, body.prompt, {
      workflowId: body.workflowId,
    });
    res.status(201).json({ id });
  });

  addRoute("GET", "/tasks/:id", async (req, res) => {
    const task = await client.getTask(req.params.id);
    res.status(200).json(task);
  });

  addRoute("POST", "/tasks/:id/wait", async (req, res) => {
    const task = await client.waitForTask(req.params.id, pollInterval, taskTimeout);
    res.status(200).json(task);
  });

  addRoute("GET", "/tasks/:id/stream", async (req, res) => {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    let closed = false;
    const reqWithEvents = req as unknown as { on?: (e: string, cb: () => void) => void };
    if (reqWithEvents.on) {
      reqWithEvents.on("close", () => {
        closed = true;
      });
    }

    try {
      for await (const update of streamTaskUpdates(baseUrl, req.params.id, {
        apiKey: options.apiKey,
      })) {
        if (closed) break;
        res.write(`data: ${JSON.stringify(update)}\n\n`);
      }
    } catch (err) {
      if (!closed) {
        res.write(`event: error\ndata: ${JSON.stringify({ error: String(err) })}\n\n`);
      }
    } finally {
      if (!closed) {
        res.end();
      }
    }
  });

  // ── Workflow routes ─────────────────────────────────────────────────────

  addRoute("POST", "/workflows", async (req, res) => {
    const definition = req.body as {
      Id?: string;
      Nodes?: unknown[];
      Edges?: unknown[];
    } | undefined;
    if (!definition?.Id || !definition?.Nodes) {
      res.status(400).json({ error: "Missing required fields: Id, Nodes" });
      return;
    }
    await client.createWorkflow(definition as Parameters<typeof client.createWorkflow>[0]);
    res.status(201).json({ id: definition.Id });
  });

  addRoute("GET", "/workflows", async (_req, res) => {
    const workflows = await client.listWorkflows();
    res.status(200).json(workflows);
  });

  addRoute("POST", "/workflows/:id/start", async (req, res) => {
    await client.startWorkflow(req.params.id);
    res.status(202).json({ status: "started" });
  });

  addRoute("GET", "/workflows/:id/nodes", async (req, res) => {
    const nodes = await client.getWorkflowNodes(req.params.id);
    res.status(200).json(nodes);
  });

  addRoute("POST", "/workflows/:wid/nodes/:nid/approve", async (req, res) => {
    await client.approveNode(req.params.wid, req.params.nid);
    res.status(200).json({ status: "approved" });
  });

  addRoute("POST", "/workflows/:wid/nodes/:nid/reject", async (req, res) => {
    await client.rejectNode(req.params.wid, req.params.nid);
    res.status(200).json({ status: "rejected" });
  });

  // ── Main middleware dispatcher ──────────────────────────────────────────

  return function orchestratorMiddleware(req: Request, res: Response, next: NextFunction) {
    const method = req.method.toUpperCase();
    const path = req.path || "/";

    for (const route of routes) {
      if (route.method !== method) continue;
      const match = path.match(route.pattern);
      if (!match) continue;

      // Populate params from regex captures
      const params: Record<string, string> = {};
      route.paramNames.forEach((name, i) => {
        params[name] = decodeURIComponent(match[i + 1]);
      });
      const proxiedReq = { ...req, params: { ...req.params, ...params } };

      route.handler(proxiedReq as Request, res, (err?: unknown) => {
        if (err) {
          if (err instanceof OrchestratorError && err.statusCode) {
            res.status(err.statusCode).json({ error: err.message });
          } else {
            next(err);
          }
        }
      });
      return;
    }

    // No matching route — pass to next middleware
    next();
  };
}
