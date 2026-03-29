using System;
using System.Threading;
using System.Threading.Tasks;


namespace Orchestrator.Core
{
    public record TaskDefinition(string Id, string AgentType, string Prompt, string WorkflowId = null);
    public record AgentContext(string TaskId, string WorkflowId, string Language, string Priority);
    public record AgentResult(string TaskId, bool Success, string Output, string Error = null);

    public interface IAgent
    {
        string AgentType { get; }
        Task<AgentResult> ExecuteAsync(TaskDefinition task, AgentContext context, CancellationToken cancellationToken);
    }
}
