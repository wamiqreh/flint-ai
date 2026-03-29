using System.Net;
using System.Net.Http.Json;
using System.Text.Json;

namespace Flint.AI.Sdk;

/// <summary>
/// HTTP client for the Flint API.
/// Supports task submission, polling, batch operations, and workflow management.
/// </summary>
public sealed class OrchestratorClient : IDisposable
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        Converters = { new System.Text.Json.Serialization.JsonStringEnumConverter() }
    };

    private readonly HttpClient _http;
    private readonly OrchestratorClientOptions _options;
    private bool _disposed;

    public OrchestratorClient(OrchestratorClientOptions options)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _http = new HttpClient
        {
            BaseAddress = new Uri(options.BaseUrl.TrimEnd('/')),
            Timeout = TimeSpan.FromSeconds(options.TimeoutSeconds)
        };

        if (!string.IsNullOrEmpty(options.ApiKey))
            _http.DefaultRequestHeaders.Add("X-API-Key", options.ApiKey);
    }

    public OrchestratorClient(string baseUrl, string? apiKey = null)
        : this(new OrchestratorClientOptions { BaseUrl = baseUrl, ApiKey = apiKey })
    {
    }

    // ── Tasks ───────────────────────────────────────────────────────────

    /// <summary>Submit a single task and return its ID.</summary>
    public async Task<string> SubmitTaskAsync(
        string agentType,
        string prompt,
        Dictionary<string, string>? metadata = null,
        CancellationToken ct = default)
    {
        var body = new TaskSubmission
        {
            AgentType = agentType,
            Prompt = prompt,
            Metadata = metadata
        };

        using var response = await SendWithRetryAsync(
            () => new HttpRequestMessage(HttpMethod.Post, "/tasks")
            {
                Content = JsonContent.Create(body, options: JsonOptions)
            }, ct).ConfigureAwait(false);

        var result = await DeserializeAsync<SubmitTaskResponse>(response, ct).ConfigureAwait(false);
        return result.Id;
    }

    /// <summary>Retrieve a task by its ID.</summary>
    public async Task<TaskRecord> GetTaskAsync(string taskId, CancellationToken ct = default)
    {
        using var response = await SendWithRetryAsync(
            () => new HttpRequestMessage(HttpMethod.Get, $"/tasks/{Uri.EscapeDataString(taskId)}"),
            ct).ConfigureAwait(false);

        return await DeserializeAsync<TaskRecord>(response, ct).ConfigureAwait(false);
    }

    /// <summary>Poll until the task reaches a terminal state.</summary>
    public async Task<TaskRecord> WaitForTaskAsync(
        string taskId,
        TimeSpan? pollInterval = null,
        TimeSpan? timeout = null,
        CancellationToken ct = default)
    {
        var interval = pollInterval ?? TimeSpan.FromSeconds(1);
        using var cts = timeout.HasValue
            ? CancellationTokenSource.CreateLinkedTokenSource(ct)
            : CancellationTokenSource.CreateLinkedTokenSource(ct);

        if (timeout.HasValue)
            cts.CancelAfter(timeout.Value);

        while (true)
        {
            var task = await GetTaskAsync(taskId, cts.Token).ConfigureAwait(false);
            if (task.State is TaskState.Succeeded or TaskState.Failed or TaskState.DeadLetter)
                return task;

            await Task.Delay(interval, cts.Token).ConfigureAwait(false);
        }
    }

    /// <summary>Submit multiple tasks in parallel, returning their IDs.</summary>
    public async Task<List<string>> SubmitTasksAsync(
        IEnumerable<TaskSubmission> tasks,
        CancellationToken ct = default)
    {
        var submissions = tasks.Select(t =>
            SubmitTaskAsync(t.AgentType, t.Prompt, t.Metadata, ct));

        var ids = await Task.WhenAll(submissions).ConfigureAwait(false);
        return ids.ToList();
    }

    // ── Workflows ───────────────────────────────────────────────────────

    /// <summary>Create a new workflow definition.</summary>
    public async Task<WorkflowDefinition> CreateWorkflowAsync(
        WorkflowDefinition workflow,
        CancellationToken ct = default)
    {
        using var response = await SendWithRetryAsync(
            () => new HttpRequestMessage(HttpMethod.Post, "/workflows")
            {
                Content = JsonContent.Create(workflow, options: JsonOptions)
            }, ct).ConfigureAwait(false);

        return await DeserializeAsync<WorkflowDefinition>(response, ct).ConfigureAwait(false);
    }

    /// <summary>Start an existing workflow.</summary>
    public async Task StartWorkflowAsync(string workflowId, CancellationToken ct = default)
    {
        using var response = await SendWithRetryAsync(
            () => new HttpRequestMessage(HttpMethod.Post, $"/workflows/{Uri.EscapeDataString(workflowId)}/start"),
            ct).ConfigureAwait(false);
    }

    /// <summary>List all workflow definitions.</summary>
    public async Task<List<WorkflowDefinition>> ListWorkflowsAsync(CancellationToken ct = default)
    {
        using var response = await SendWithRetryAsync(
            () => new HttpRequestMessage(HttpMethod.Get, "/workflows"),
            ct).ConfigureAwait(false);

        return await DeserializeAsync<List<WorkflowDefinition>>(response, ct).ConfigureAwait(false);
    }

    /// <summary>Approve a workflow node that requires human approval.</summary>
    public async Task ApproveNodeAsync(
        string workflowId, string nodeId, CancellationToken ct = default)
    {
        using var response = await SendWithRetryAsync(
            () => new HttpRequestMessage(HttpMethod.Post,
                $"/workflows/{Uri.EscapeDataString(workflowId)}/nodes/{Uri.EscapeDataString(nodeId)}/approve"),
            ct).ConfigureAwait(false);
    }

    /// <summary>Reject a workflow node that requires human approval.</summary>
    public async Task RejectNodeAsync(
        string workflowId, string nodeId, CancellationToken ct = default)
    {
        using var response = await SendWithRetryAsync(
            () => new HttpRequestMessage(HttpMethod.Post,
                $"/workflows/{Uri.EscapeDataString(workflowId)}/nodes/{Uri.EscapeDataString(nodeId)}/reject"),
            ct).ConfigureAwait(false);
    }

    // ── Internals ───────────────────────────────────────────────────────

    private async Task<HttpResponseMessage> SendWithRetryAsync(
        Func<HttpRequestMessage> requestFactory,
        CancellationToken ct)
    {
        int attempt = 0;
        while (true)
        {
            using var request = requestFactory();
            HttpResponseMessage? response = null;
            try
            {
                response = await _http.SendAsync(request, ct).ConfigureAwait(false);
                MapErrorResponse(response, request.RequestUri?.AbsolutePath);
                return response;
            }
            catch (OrchestratorException)
            {
                response?.Dispose();
                throw;
            }
            catch (HttpRequestException) when (attempt < _options.MaxRetries)
            {
                response?.Dispose();
                attempt++;
                var delay = TimeSpan.FromMilliseconds(200 * Math.Pow(2, attempt));
                await Task.Delay(delay, ct).ConfigureAwait(false);
            }
            catch
            {
                response?.Dispose();
                throw;
            }
        }
    }

    private static void MapErrorResponse(HttpResponseMessage response, string? path)
    {
        if (response.IsSuccessStatusCode)
            return;

        var status = response.StatusCode;

        // Extract task ID from path like "/tasks/{id}"
        string? taskId = null;
        if (path is not null)
        {
            var segments = path.Split('/', StringSplitOptions.RemoveEmptyEntries);
            if (segments.Length >= 2 && segments[0] == "tasks")
                taskId = segments[1];
        }

        throw status switch
        {
            HttpStatusCode.NotFound when taskId is not null
                => new TaskNotFoundException(taskId),
            HttpStatusCode.NotFound
                => new OrchestratorException("Resource not found.", status),
            HttpStatusCode.TooManyRequests
                => new RateLimitException(
                    response.Headers.RetryAfter?.Delta),
            HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden
                => new AuthenticationException(),
            HttpStatusCode.BadRequest or HttpStatusCode.UnprocessableEntity
                => new WorkflowValidationException(
                    $"Validation error ({(int)status})."),
            _ => new OrchestratorException(
                $"HTTP {(int)status} {status}.", status)
        };
    }

    private static async Task<T> DeserializeAsync<T>(
        HttpResponseMessage response, CancellationToken ct)
    {
        return await response.Content.ReadFromJsonAsync<T>(JsonOptions, ct).ConfigureAwait(false)
            ?? throw new OrchestratorException("Response body was null.");
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            _http.Dispose();
            _disposed = true;
        }
    }
}
