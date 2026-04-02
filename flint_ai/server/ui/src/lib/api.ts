const BASE = '';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, `${res.status}: ${text}`);
  }
  return res.json();
}

export interface Task {
  id: string;
  agent_type: string;
  prompt: string;
  state: string;
  priority: number;
  attempt: number;
  max_retries: number;
  result_json?: string;
  error?: string;
  workflow_id?: string;
  node_id?: string;
  created_at: string;
  updated_at?: string;
  started_at?: string;
  completed_at?: string;
  metadata?: Record<string, unknown>;
}

export interface DashboardSummary {
  total: number;
  by_state: Record<string, number>;
  queue_length: number;
  dlq_length: number;
}

export interface ConcurrencyInfo {
  [agent: string]: { limit: number; used: number };
}

export interface WorkflowDef {
  id: string;
  name?: string;
  description?: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  created_at?: string;
}

export interface WorkflowNode {
  id: string;
  agent_type: string;
  prompt_template: string;
  human_approval?: boolean;
  max_retries?: number;
  dead_letter_on_failure?: boolean;
  sub_workflow_id?: string;
  map_variable?: string;
}

export interface WorkflowEdge {
  from_node_id: string;
  to_node_id: string;
  condition?: {
    on_status?: string[];
    expression?: string;
  };
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  state: string;
  node_states: Record<string, string>;
  task_ids: Record<string, string>;
  started_at: string;
  completed_at?: string;
}

export interface AgentInfo {
  agent_type: string;
  healthy: boolean;
}

export interface DLQMessage {
  message_id: string;
  task_id: string;
  data: Record<string, unknown>;
}

export interface HealthStatus {
  status: string;
  checks: Record<string, string>;
}

// Dashboard
export const fetchSummary = () => request<DashboardSummary>('/dashboard/summary');
export const fetchConcurrency = () => request<ConcurrencyInfo>('/dashboard/concurrency');
export const fetchApprovals = () => request<Task[]>('/dashboard/approvals');

// Tasks
export const fetchTasks = (params?: string) =>
  request<Task[]>(`/tasks${params ? `?${params}` : ''}`);
export const submitTask = (body: { agent_type: string; prompt: string; priority?: number }) =>
  request<Task>('/tasks', { method: 'POST', body: JSON.stringify(body) });
export const cancelTask = (id: string) =>
  request<void>(`/tasks/${id}/cancel`, { method: 'POST' });
export const restartTask = (id: string) =>
  request<Task>(`/tasks/${id}/restart`, { method: 'POST' });
export const approveTask = (id: string) =>
  request<void>(`/tasks/${id}/approve`, { method: 'POST' });
export const rejectTask = (id: string) =>
  request<void>(`/tasks/${id}/reject`, { method: 'POST' });

// Workflows
export const fetchWorkflows = () => request<WorkflowDef[]>('/workflows');
export const fetchWorkflow = (id: string) => request<WorkflowDef>(`/workflows/${id}`);
export const createWorkflow = (body: Partial<WorkflowDef>) =>
  request<WorkflowDef>('/workflows', { method: 'POST', body: JSON.stringify(body) });
export const updateWorkflow = (id: string, body: Partial<WorkflowDef>) =>
  request<WorkflowDef>(`/workflows/${id}`, { method: 'PUT', body: JSON.stringify(body) });
export const deleteWorkflow = (id: string) =>
  request<void>(`/workflows/${id}`, { method: 'DELETE' });
export const startWorkflow = (id: string, input?: Record<string, unknown>) =>
  request<WorkflowRun>(`/workflows/${id}/start`, {
    method: 'POST',
    body: JSON.stringify(input ?? {}),
  });
export const fetchWorkflowRuns = (id: string) =>
  request<WorkflowRun[]>(`/workflows/${id}/runs`);

// DLQ
export const fetchDLQ = () => request<DLQMessage[]>('/dashboard/dlq');
export const retryDLQ = (messageId: string) =>
  request<void>(`/dashboard/dlq/${messageId}/retry`, { method: 'POST' });
export const purgeDLQ = () =>
  request<{ purged: number }>('/dashboard/dlq/purge', { method: 'POST' });

// Agents
export const fetchAgents = () => request<AgentInfo[]>('/agents');

// Health
export const fetchHealth = () => request<HealthStatus>('/health');

// SSE helper
export function subscribeTask(taskId: string, onEvent: (data: unknown) => void): EventSource {
  const es = new EventSource(`/tasks/${taskId}/stream`);
  es.onmessage = (e) => onEvent(JSON.parse(e.data));
  return es;
}
