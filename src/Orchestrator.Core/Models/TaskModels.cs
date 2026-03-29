

namespace Orchestrator.Core.Models{    public record TaskDefinition(string Id, string AgentType, string Prompt, string WorkflowId = null);
record AgentContext(string TaskId, string WorkflowId, string Language, string Priority);
record AgentResult(string TaskId, bool Success, string Output, string Error = null);}

