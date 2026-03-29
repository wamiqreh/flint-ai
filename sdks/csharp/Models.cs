using System.Text.Json.Serialization;

namespace Flint.AI.Sdk;

/// <summary>Task states matching the server-side TaskState enum.</summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
public enum TaskState
{
    Pending,
    Queued,
    Running,
    Succeeded,
    Failed,
    DeadLetter
}

/// <summary>Payload sent when submitting a new task.</summary>
public sealed class TaskSubmission
{
    [JsonPropertyName("AgentType")]
    public required string AgentType { get; init; }

    [JsonPropertyName("Prompt")]
    public required string Prompt { get; init; }

    [JsonPropertyName("WorkflowId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? WorkflowId { get; init; }

    [JsonPropertyName("Metadata")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, string>? Metadata { get; init; }
}

/// <summary>Server response after submitting a task.</summary>
public sealed class SubmitTaskResponse
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = string.Empty;
}

/// <summary>Full task record returned by the API.</summary>
public sealed class TaskRecord
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = string.Empty;

    [JsonPropertyName("agentType")]
    public string AgentType { get; init; } = string.Empty;

    [JsonPropertyName("prompt")]
    public string Prompt { get; init; } = string.Empty;

    [JsonPropertyName("state")]
    public TaskState State { get; init; }

    [JsonPropertyName("result")]
    public string? Result { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }

    [JsonPropertyName("workflowId")]
    public string? WorkflowId { get; init; }

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("completedAt")]
    public DateTimeOffset? CompletedAt { get; init; }
}

/// <summary>Structured result returned by an agent execution.</summary>
public sealed class AgentResult
{
    [JsonPropertyName("taskId")]
    public string TaskId { get; init; } = string.Empty;

    [JsonPropertyName("success")]
    public bool Success { get; init; }

    [JsonPropertyName("output")]
    public string? Output { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }

    [JsonPropertyName("tokensUsed")]
    public int? TokensUsed { get; init; }

    [JsonPropertyName("durationMs")]
    public long? DurationMs { get; init; }
}

/// <summary>A single node inside a workflow graph.</summary>
public sealed class WorkflowNode
{
    [JsonPropertyName("Id")]
    public required string Id { get; init; }

    [JsonPropertyName("AgentType")]
    public required string AgentType { get; init; }

    [JsonPropertyName("PromptTemplate")]
    public required string PromptTemplate { get; init; }

    [JsonPropertyName("MaxRetries")]
    public int MaxRetries { get; init; } = 3;

    [JsonPropertyName("DeadLetterOnFailure")]
    public bool DeadLetterOnFailure { get; init; } = true;

    [JsonPropertyName("HumanApproval")]
    public bool HumanApproval { get; init; }
}

/// <summary>A directed edge connecting two workflow nodes.</summary>
public sealed class WorkflowEdge
{
    [JsonPropertyName("FromNodeId")]
    public required string FromNodeId { get; init; }

    [JsonPropertyName("ToNodeId")]
    public required string ToNodeId { get; init; }

    [JsonPropertyName("Condition")]
    public string Condition { get; init; } = string.Empty;
}

/// <summary>Complete workflow definition with nodes and edges.</summary>
public sealed class WorkflowDefinition
{
    [JsonPropertyName("Id")]
    public required string Id { get; init; }

    [JsonPropertyName("Nodes")]
    public List<WorkflowNode> Nodes { get; init; } = [];

    [JsonPropertyName("Edges")]
    public List<WorkflowEdge> Edges { get; init; } = [];
}
