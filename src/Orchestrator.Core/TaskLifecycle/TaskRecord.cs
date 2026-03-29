using System;


namespace Orchestrator.Core.TaskLifecycle
{
    public record TaskRecord(
        string Id,
        string AgentType,
        string Prompt,
        string WorkflowId,
        TaskState State,
        string ResultJson = null,
        DateTimeOffset CreatedAt = default
    );
}
