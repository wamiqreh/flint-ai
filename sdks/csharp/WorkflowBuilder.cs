namespace Flint.AI.Sdk;

/// <summary>
/// Fluent builder for constructing <see cref="WorkflowDefinition"/> instances.
/// </summary>
public sealed class WorkflowBuilder
{
    private readonly string _id;
    private readonly List<WorkflowNode> _nodes = [];
    private readonly List<WorkflowEdge> _edges = [];

    public WorkflowBuilder(string workflowId)
    {
        _id = workflowId ?? throw new ArgumentNullException(nameof(workflowId));
    }

    /// <summary>Add a node to the workflow.</summary>
    public WorkflowBuilder AddNode(
        string id,
        string agentType,
        string promptTemplate,
        int maxRetries = 3,
        bool deadLetterOnFailure = true,
        bool humanApproval = false)
    {
        _nodes.Add(new WorkflowNode
        {
            Id = id,
            AgentType = agentType,
            PromptTemplate = promptTemplate,
            MaxRetries = maxRetries,
            DeadLetterOnFailure = deadLetterOnFailure,
            HumanApproval = humanApproval
        });
        return this;
    }

    /// <summary>Add an edge connecting two nodes.</summary>
    public WorkflowBuilder AddEdge(string fromNodeId, string toNodeId, string condition = "")
    {
        _edges.Add(new WorkflowEdge
        {
            FromNodeId = fromNodeId,
            ToNodeId = toNodeId,
            Condition = condition
        });
        return this;
    }

    /// <summary>Build the final <see cref="WorkflowDefinition"/>.</summary>
    public WorkflowDefinition Build()
    {
        if (_nodes.Count == 0)
            throw new WorkflowValidationException("Workflow must contain at least one node.");

        // Validate that all edge references point to known nodes
        var nodeIds = new HashSet<string>(_nodes.Select(n => n.Id));
        foreach (var edge in _edges)
        {
            if (!nodeIds.Contains(edge.FromNodeId))
                throw new WorkflowValidationException($"Edge references unknown source node '{edge.FromNodeId}'.");
            if (!nodeIds.Contains(edge.ToNodeId))
                throw new WorkflowValidationException($"Edge references unknown target node '{edge.ToNodeId}'.");
        }

        return new WorkflowDefinition
        {
            Id = _id,
            Nodes = [.. _nodes],
            Edges = [.. _edges]
        };
    }
}
