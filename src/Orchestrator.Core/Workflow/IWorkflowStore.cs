using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Core.Workflow
{
    public interface IWorkflowStore
    {
        Task CreateAsync(WorkflowDefinition def, CancellationToken cancellationToken = default);
        Task<WorkflowDefinition> GetAsync(string id, CancellationToken cancellationToken = default);
        Task SetNodeTaskMappingAsync(string workflowId, string nodeId, string taskId, CancellationToken cancellationToken = default);
        Task<string> GetTaskIdForNodeAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default);
        Task<string> GetNodeIdForTaskAsync(string workflowId, string taskId, CancellationToken cancellationToken = default);
        // per-node attempt tracking
        Task<int> GetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default);
        Task<int> IncrementAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default);
        Task ResetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default);
        // list definitions (for dashboard / UI)
        Task<IEnumerable<WorkflowDefinition>> ListAsync(CancellationToken cancellationToken = default);
    }
}
