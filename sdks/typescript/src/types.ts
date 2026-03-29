// ── Task types ──────────────────────────────────────────────────────────────

/** Terminal and intermediate task states matching the C# state machine. */
export enum TaskState {
  Pending = "Pending",
  Queued = "Queued",
  Running = "Running",
  Succeeded = "Succeeded",
  Failed = "Failed",
  DeadLetter = "DeadLetter",
}

/** Payload sent to `POST /tasks`. */
export interface TaskSubmission {
  AgentType: string;
  Prompt: string;
  WorkflowId?: string;
}

/** Response returned by `GET /tasks/{id}` and streamed via SSE / WebSocket. */
export interface TaskRecord {
  id: string;
  state: TaskState;
  result: string | null;
  workflowId: string | null;
}

/** Convenience alias for the `POST /tasks` response. */
export interface SubmitTaskResponse {
  id: string;
}

// ── Workflow types ──────────────────────────────────────────────────────────

export interface WorkflowNode {
  Id: string;
  AgentType: string;
  PromptTemplate: string;
  MaxRetries?: number;
  DeadLetterOnFailure?: boolean;
  HumanApproval?: boolean;
}

export interface WorkflowEdge {
  FromNodeId: string;
  ToNodeId: string;
  Condition?: string;
}

export interface WorkflowDefinition {
  Id: string;
  Nodes: WorkflowNode[];
  Edges: WorkflowEdge[];
}

// ── Agent result (generic wrapper) ─────────────────────────────────────────

export interface AgentResult {
  taskId: string;
  state: TaskState;
  result: string | null;
}

// ── Client options ─────────────────────────────────────────────────────────

export interface OrchestratorClientOptions {
  /** API key sent as `X-API-Key` header. */
  apiKey?: string;
  /** Request timeout in milliseconds (default 30 000). */
  timeout?: number;
  /** Maximum number of retries on transient errors (default 3). */
  retries?: number;
  /** Base delay in ms for exponential backoff (default 500). */
  retryBaseDelay?: number;
}

// ── Batch helpers ──────────────────────────────────────────────────────────

export interface BatchTaskInput {
  agentType: string;
  prompt: string;
  workflowId?: string;
}

// ── Dashboard / observability ──────────────────────────────────────────────

export interface AgentConcurrency {
  agent: string;
  limit: number;
  used: number;
}
