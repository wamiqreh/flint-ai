using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.Workflow;
using Orchestrator.Core.TaskLifecycle;

namespace Orchestrator.Infrastructure.Workflow
{
    public partial class WorkflowEngine
    {
        public async Task OnTaskFailedAsync(string taskId, string workflowId, CancellationToken cancellationToken = default)
        {
            if (string.IsNullOrEmpty(workflowId)) return;
            var def = await _store.GetAsync(workflowId, cancellationToken);
            if (def == null) return;
            var nodeId = await _store.GetNodeIdForTaskAsync(workflowId, taskId, cancellationToken);
            if (string.IsNullOrEmpty(nodeId)) return;
            var node = def.Nodes.Find(n => n.Id == nodeId);
            if (node == null) return;
            var attempts = await _store.IncrementAttemptCountAsync(workflowId, nodeId, cancellationToken);
            if (attempts <= node.MaxRetries)
            {
                // retry: enqueue a new task for the same node
                var newId = System.Guid.NewGuid().ToString();
                var record = new TaskRecord(newId, node.AgentType, node.PromptTemplate, def.Id, TaskState.Queued, null, System.DateTimeOffset.UtcNow);
                await _taskStore.CreateAsync(record, cancellationToken);
                await _store.SetNodeTaskMappingAsync(def.Id, node.Id, newId, cancellationToken);
                var payload = System.Text.Json.JsonSerializer.Serialize(new { Id = newId });
                await _queue.EnqueueAsync("tasks", payload, cancellationToken);
                return;
            }
            // exceeded retries
            if (node.HumanApproval)
            {
                // mark task as dead-lettered awaiting human approval -- for now, set state to DeadLetter
                await _taskStore.UpdateStateAsync(taskId, TaskState.DeadLetter, cancellationToken);
                return;
            }
            if (node.DeadLetterOnFailure)
            {
                await _taskStore.UpdateStateAsync(taskId, TaskState.DeadLetter, cancellationToken);
                return;
            }
            // default: mark as Failed
            await _taskStore.UpdateStateAsync(taskId, TaskState.Failed, cancellationToken);
        }
    }
}
