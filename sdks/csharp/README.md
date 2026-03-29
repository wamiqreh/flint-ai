# Flint C# SDK

A typed C# client for the **Flint** HTTP API, providing task submission, polling, batch operations, workflow management, and a fluent workflow builder.

## Installation

Add a project reference or (when published) install from NuGet:

```
dotnet add package Flint.AI
```

## Quick start

```csharp
using Flint.AI.Sdk;

// Create the client
using var client = new OrchestratorClient("http://localhost:5156");

// Submit a task
var taskId = await client.SubmitTaskAsync("openai", "Summarise this document");

// Poll until complete
var result = await client.WaitForTaskAsync(taskId, timeout: TimeSpan.FromMinutes(5));
Console.WriteLine($"State: {result.State}, Result: {result.Result}");
```

## Configuration

```csharp
var client = new OrchestratorClient(new OrchestratorClientOptions
{
    BaseUrl     = "https://orchestrator.example.com",
    ApiKey      = "sk-...",
    TimeoutSeconds = 60,
    MaxRetries     = 5
});
```

The API key is sent as the `X-API-Key` header on every request.

## Tasks

```csharp
// Single task
string id = await client.SubmitTaskAsync("dummy", "Hello");

// Get status
TaskRecord task = await client.GetTaskAsync(id);

// Wait with custom interval
TaskRecord done = await client.WaitForTaskAsync(id,
    pollInterval: TimeSpan.FromSeconds(2),
    timeout: TimeSpan.FromMinutes(10));

// Batch submit
var ids = await client.SubmitTasksAsync(new[]
{
    new TaskSubmission { AgentType = "openai", Prompt = "Task 1" },
    new TaskSubmission { AgentType = "openai", Prompt = "Task 2" }
});
```

## Workflows

### Using the fluent builder

```csharp
var workflow = new WorkflowBuilder("ci-pipeline")
    .AddNode("gen",  "openai", "Generate code")
    .AddNode("test", "dummy",  "Run tests", humanApproval: true)
    .AddEdge("gen", "test")
    .Build();

await client.CreateWorkflowAsync(workflow);
await client.StartWorkflowAsync("ci-pipeline");
```

### Human approval

```csharp
// Approve or reject a node that requires human review
await client.ApproveNodeAsync("ci-pipeline", "test");
// or
await client.RejectNodeAsync("ci-pipeline", "test");
```

### Listing workflows

```csharp
List<WorkflowDefinition> workflows = await client.ListWorkflowsAsync();
```

## Error handling

The SDK maps HTTP errors to typed exceptions:

| HTTP status | Exception |
|---|---|
| 404 | `TaskNotFoundException` |
| 400 / 422 | `WorkflowValidationException` |
| 429 | `RateLimitException` |
| 401 / 403 | `AuthenticationException` |
| Other | `OrchestratorException` |

```csharp
try
{
    await client.GetTaskAsync("nonexistent");
}
catch (TaskNotFoundException ex)
{
    Console.WriteLine($"Not found: {ex.TaskId}");
}
catch (RateLimitException ex)
{
    Console.WriteLine($"Retry after: {ex.RetryAfter}");
}
```

## Retry behaviour

Transient `HttpRequestException` errors are retried up to `MaxRetries` times with exponential backoff (200 ms × 2^attempt). Non-transient HTTP errors (4xx/5xx with specific semantics) are mapped to exceptions immediately.
