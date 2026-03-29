using System.Net;

namespace Flint.AI.Sdk;

/// <summary>Base exception for all orchestrator SDK errors.</summary>
public class OrchestratorException : Exception
{
    public HttpStatusCode? StatusCode { get; }

    public OrchestratorException(string message, HttpStatusCode? statusCode = null, Exception? inner = null)
        : base(message, inner)
    {
        StatusCode = statusCode;
    }
}

/// <summary>Thrown when the requested task does not exist (HTTP 404).</summary>
public class TaskNotFoundException : OrchestratorException
{
    public string TaskId { get; }

    public TaskNotFoundException(string taskId)
        : base($"Task '{taskId}' not found.", HttpStatusCode.NotFound)
    {
        TaskId = taskId;
    }
}

/// <summary>Thrown when a workflow definition is invalid (HTTP 400/422).</summary>
public class WorkflowValidationException : OrchestratorException
{
    public WorkflowValidationException(string message)
        : base(message, HttpStatusCode.BadRequest) { }
}

/// <summary>Thrown when the server returns HTTP 429.</summary>
public class RateLimitException : OrchestratorException
{
    public TimeSpan? RetryAfter { get; }

    public RateLimitException(TimeSpan? retryAfter = null)
        : base("Rate limit exceeded.", HttpStatusCode.TooManyRequests)
    {
        RetryAfter = retryAfter;
    }
}

/// <summary>Thrown when the API key is missing or invalid (HTTP 401/403).</summary>
public class AuthenticationException : OrchestratorException
{
    public AuthenticationException(string message = "Authentication failed.")
        : base(message, HttpStatusCode.Unauthorized) { }
}
