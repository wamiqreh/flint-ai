/** Base error for all orchestrator SDK errors. */
export class OrchestratorError extends Error {
  public readonly statusCode: number | undefined;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "OrchestratorError";
    this.statusCode = statusCode;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Thrown when a task ID cannot be found (HTTP 404). */
export class TaskNotFoundError extends OrchestratorError {
  public readonly taskId: string;

  constructor(taskId: string) {
    super(`Task not found: ${taskId}`, 404);
    this.name = "TaskNotFoundError";
    this.taskId = taskId;
  }
}

/** Thrown when a workflow definition is invalid (HTTP 400). */
export class WorkflowValidationError extends OrchestratorError {
  constructor(message: string) {
    super(message, 400);
    this.name = "WorkflowValidationError";
  }
}

/** Thrown when the server returns HTTP 429. */
export class RateLimitError extends OrchestratorError {
  /** Seconds until the client may retry (from `Retry-After` header). */
  public readonly retryAfter: number | undefined;

  constructor(retryAfter?: number) {
    super(
      retryAfter
        ? `Rate limited – retry after ${retryAfter}s`
        : "Rate limited",
      429,
    );
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

/** Thrown when the API key is missing or invalid (HTTP 401). */
export class AuthenticationError extends OrchestratorError {
  constructor(message = "Missing or invalid X-API-Key") {
    super(message, 401);
    this.name = "AuthenticationError";
  }
}

/** Thrown when `waitForTask` exceeds its timeout. */
export class TimeoutError extends OrchestratorError {
  constructor(message = "Operation timed out") {
    super(message);
    this.name = "TimeoutError";
  }
}
