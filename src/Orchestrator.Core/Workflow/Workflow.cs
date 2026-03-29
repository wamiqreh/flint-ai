using System;
using System.Collections.Generic;


namespace Orchestrator.Core.Workflow
{
    public record WorkflowNode(string Id, string AgentType, string PromptTemplate, int MaxRetries = 3, bool DeadLetterOnFailure = true, bool HumanApproval = false);
    public record WorkflowEdge(string FromNodeId, string ToNodeId, string Condition = "");
    public class WorkflowDefinition
    {
        public string Id { get; set; }
        public List<WorkflowNode> Nodes { get; set; } = new();
        public List<WorkflowEdge> Edges { get; set; } = new();
    }
}
