import type {
  BatchTaskInput,
  OrchestratorClientOptions,
  SubmitTaskResponse,
  TaskRecord,
  TaskSubmission,
  WorkflowDefinition,
  WorkflowNode,
} from "./types.js";
import { TaskState } from "./types.js";
import {
  AuthenticationError,
  OrchestratorError,
  RateLimitError,
  TaskNotFoundError,
  TimeoutError,
  WorkflowValidationError,
} from "./errors.js";

const TERMINAL_STATES = new Set<string>([
  TaskState.Succeeded,
  TaskState.Failed,
  TaskState.DeadLetter,
]);

const DEFAULT_TIMEOUT = 30_000;
const DEFAULT_RETRIES = 3;
const DEFAULT_RETRY_BASE_DELAY = 500;

export class OrchestratorClient {
  private readonly baseUrl: string;
  private readonly apiKey: string | undefined;
  private readonly timeout: number;
  private readonly retries: number;
  private readonly retryBaseDelay: number;

  constructor(baseUrl = "http://localhost:5156", options?: OrchestratorClientOptions) {
    // Strip trailing slash
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.apiKey = options?.apiKey;
    this.timeout = options?.timeout ?? DEFAULT_TIMEOUT;
    this.retries = options?.retries ?? DEFAULT_RETRIES;
    this.retryBaseDelay = options?.retryBaseDelay ?? DEFAULT_RETRY_BASE_DELAY;
  }

  // ── Task endpoints ──────────────────────────────────────────────────────

  /** Submit a single task. Returns the newly created task ID. */
  async submitTask(
    agentType: string,
    prompt: string,
    metadata?: { workflowId?: string },
  ): Promise<string> {
    const body: TaskSubmission = {
      AgentType: agentType,
      Prompt: prompt,
      ...(metadata?.workflowId ? { WorkflowId: metadata.workflowId } : {}),
    };
    const res = await this.request<SubmitTaskResponse>("POST", "/tasks", body);
    return res.id;
  }

  /** Get the current state of a task. */
  async getTask(taskId: string): Promise<TaskRecord> {
    return this.request<TaskRecord>("GET", `/tasks/${encodeURIComponent(taskId)}`);
  }

  /**
   * Poll a task until it reaches a terminal state.
   * @param pollInterval  Milliseconds between polls (default 1 000).
   * @param timeout       Maximum wait in milliseconds (default 300 000 = 5 min).
   */
  async waitForTask(
    taskId: string,
    pollInterval = 1_000,
    timeout = 300_000,
  ): Promise<TaskRecord> {
    const deadline = Date.now() + timeout;

    while (Date.now() < deadline) {
      const task = await this.getTask(taskId);
      if (TERMINAL_STATES.has(task.state)) {
        return task;
      }
      const remaining = deadline - Date.now();
      if (remaining <= 0) break;
      await sleep(Math.min(pollInterval, remaining));
    }

    throw new TimeoutError(
      `Task ${taskId} did not complete within ${timeout}ms`,
    );
  }

  /** Submit multiple tasks in parallel. Returns an array of task IDs. */
  async submitTasks(tasks: BatchTaskInput[]): Promise<string[]> {
    return Promise.all(
      tasks.map((t) => this.submitTask(t.agentType, t.prompt, { workflowId: t.workflowId })),
    );
  }

  // ── Workflow endpoints ──────────────────────────────────────────────────

  /** Create a workflow DAG definition. */
  async createWorkflow(definition: WorkflowDefinition): Promise<void> {
    await this.request<WorkflowDefinition>("POST", "/workflows", definition);
  }

  /** Start a previously created workflow. */
  async startWorkflow(workflowId: string): Promise<void> {
    await this.request<unknown>(
      "POST",
      `/workflows/${encodeURIComponent(workflowId)}/start`,
    );
  }

  /** List all workflow definitions. */
  async listWorkflows(): Promise<WorkflowDefinition[]> {
    return this.request<WorkflowDefinition[]>("GET", "/workflows");
  }

  /** Get the nodes of a specific workflow. */
  async getWorkflowNodes(workflowId: string): Promise<WorkflowNode[]> {
    return this.request<WorkflowNode[]>(
      "GET",
      `/workflows/${encodeURIComponent(workflowId)}/nodes`,
    );
  }

  /** Approve a workflow node that requires human approval. */
  async approveNode(workflowId: string, nodeId: string): Promise<void> {
    await this.request<unknown>(
      "POST",
      `/workflows/${encodeURIComponent(workflowId)}/nodes/${encodeURIComponent(nodeId)}/approve`,
    );
  }

  /** Reject a workflow node that requires human approval. */
  async rejectNode(workflowId: string, nodeId: string): Promise<void> {
    await this.request<unknown>(
      "POST",
      `/workflows/${encodeURIComponent(workflowId)}/nodes/${encodeURIComponent(nodeId)}/reject`,
    );
  }

  // ── Internal fetch with retry ───────────────────────────────────────────

  /** Build common headers for every request. */
  private headers(extra?: Record<string, string>): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...extra,
    };
    if (this.apiKey) {
      h["X-API-Key"] = this.apiKey;
    }
    return h;
  }

  /**
   * Core request helper with retry + exponential backoff + jitter.
   * Retries on 429, 502, 503, 504, and network errors.
   */
  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let lastError: unknown;

    for (let attempt = 0; attempt <= this.retries; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeout);

        const res = await fetch(url, {
          method,
          headers: this.headers(),
          body: body !== undefined ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });

        clearTimeout(timer);

        // Success
        if (res.ok) {
          const text = await res.text();
          return text ? (JSON.parse(text) as T) : (undefined as unknown as T);
        }

        // Map specific HTTP errors
        if (res.status === 401) {
          const data = await res.json().catch(() => ({}));
          throw new AuthenticationError(
            (data as Record<string, string>).message ?? "Unauthorized",
          );
        }

        if (res.status === 404) {
          // Try to extract task ID from the path
          const taskIdMatch = path.match(/^\/tasks\/([^/]+)$/);
          if (taskIdMatch) {
            throw new TaskNotFoundError(taskIdMatch[1]);
          }
          throw new OrchestratorError(`Not found: ${path}`, 404);
        }

        if (res.status === 400) {
          const data = await res.json().catch(() => ({}));
          throw new WorkflowValidationError(
            (data as Record<string, string>).error ?? "Bad request",
          );
        }

        if (res.status === 429) {
          const retryAfterHeader = res.headers.get("Retry-After");
          const retryAfter = retryAfterHeader
            ? parseInt(retryAfterHeader, 10)
            : undefined;

          // If we have retries left, wait and continue
          if (attempt < this.retries) {
            const delay = retryAfter
              ? retryAfter * 1_000
              : this.backoffDelay(attempt);
            await sleep(delay);
            continue;
          }

          throw new RateLimitError(
            retryAfter && !isNaN(retryAfter) ? retryAfter : undefined,
          );
        }

        // Retryable server errors
        if (res.status >= 500 && attempt < this.retries) {
          lastError = new OrchestratorError(
            `Server error: ${res.status}`,
            res.status,
          );
          await sleep(this.backoffDelay(attempt));
          continue;
        }

        // Non-retryable error
        const errorBody = await res.text().catch(() => "");
        throw new OrchestratorError(
          `HTTP ${res.status}: ${errorBody || res.statusText}`,
          res.status,
        );
      } catch (err) {
        // Don't retry our own typed errors (except rate limit which is handled above)
        if (
          err instanceof AuthenticationError ||
          err instanceof TaskNotFoundError ||
          err instanceof WorkflowValidationError ||
          err instanceof RateLimitError
        ) {
          throw err;
        }

        // Abort / network errors are retryable
        if (attempt < this.retries) {
          lastError = err;
          await sleep(this.backoffDelay(attempt));
          continue;
        }

        lastError = err;
      }
    }

    // All retries exhausted
    if (lastError instanceof Error) throw lastError;
    throw new OrchestratorError("Request failed after retries");
  }

  /** Exponential backoff with full jitter. */
  private backoffDelay(attempt: number): number {
    const maxDelay = this.retryBaseDelay * 2 ** attempt;
    return Math.random() * maxDelay;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
