using System;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.Workflow;
using Orchestrator.Infrastructure.Workflow.WorkflowStore;
using Orchestrator.Core.TaskLifecycle;
using Orchestrator.Core.Queue;
using System.Diagnostics;

namespace Orchestrator.Infrastructure.Workflow
{
    // Minimal workflow engine: when a task with a workflowId completes, enqueue next node(s) based on edges.
    public partial class WorkflowEngine
    {
        private static readonly ActivitySource s_activity = new ActivitySource("Orchestrator.Core.Workflow");

        private readonly IWorkflowStore _store;
        private readonly IQueueAdapter _queue;
        private readonly ITaskStore _taskStore;

        public WorkflowEngine(IWorkflowStore store, IQueueAdapter queue, ITaskStore taskStore)
        {
            _store = store;
            _queue = queue;
            _taskStore = taskStore;
        }

        public async Task OnTaskCompletedAsync(string taskId, string workflowId, CancellationToken cancellationToken = default)
        {
            using var activity = s_activity.StartActivity("OnTaskCompleted", ActivityKind.Internal);
            activity?.SetTag("workflow.id", workflowId ?? string.Empty);
            activity?.SetTag("task.id", taskId ?? string.Empty);

            if (string.IsNullOrEmpty(workflowId)) return;
            var def = await _store.GetAsync(workflowId, cancellationToken);
            if (def == null) return;

            // find node id for the completed task
            var completedNodeId = await _store.GetNodeIdForTaskAsync(workflowId, taskId, cancellationToken);
            if (string.IsNullOrEmpty(completedNodeId)) return;

            // reset attempts for this node on success
            await _store.ResetAttemptCountAsync(workflowId, completedNodeId, cancellationToken);

            foreach (var edge in def.Edges)
            {
                if (edge.FromNodeId == completedNodeId)
                {
                    // create a new TaskRecord for the to-node and enqueue
                    var node = def.Nodes.Find(n => n.Id == edge.ToNodeId);
                    if (node == null) continue;

                    var newId = Guid.NewGuid().ToString();
                    var record = new TaskRecord(newId, node.AgentType, node.PromptTemplate, def.Id, TaskState.Queued, null, DateTimeOffset.UtcNow);
                    await _taskStore.CreateAsync(record, cancellationToken);

                    // persist mapping node -> task
                    await _store.SetNodeTaskMappingAsync(def.Id, node.Id, newId, cancellationToken);

                    var payload = System.Text.Json.JsonSerializer.Serialize(new { Id = newId });
                    await _queue.EnqueueAsync("tasks", payload, cancellationToken);
                }
            }
        }
    }
}
