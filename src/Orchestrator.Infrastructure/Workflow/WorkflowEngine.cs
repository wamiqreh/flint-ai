using System;
using System.Linq;
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
                    var node = def.Nodes.Find(n => n.Id == edge.ToNodeId);
                    if (node == null) continue;

                    // Check if ALL incoming edges to this node are satisfied (all predecessor tasks succeeded)
                    var incomingEdges = def.Edges.Where(e => e.ToNodeId == node.Id).ToList();
                    bool allPredecessorsDone = true;
                    foreach (var inc in incomingEdges)
                    {
                        var predTaskId = await _store.GetTaskIdForNodeAsync(workflowId, inc.FromNodeId, cancellationToken);
                        if (string.IsNullOrEmpty(predTaskId)) { allPredecessorsDone = false; break; }
                        var predTask = await _taskStore.GetAsync(predTaskId, cancellationToken);
                        if (predTask == null || predTask.State != TaskState.Succeeded) { allPredecessorsDone = false; break; }
                    }
                    if (!allPredecessorsDone) continue;

                    // Collect outputs from all predecessor nodes and build enriched prompt
                    var prompt = await BuildEnrichedPromptAsync(node, def, workflowId, cancellationToken);

                    var newId = Guid.NewGuid().ToString();

                    // Human-in-the-loop: create task as Pending (awaiting approval) instead of Queued
                    if (node.HumanApproval)
                    {
                        var record = new TaskRecord(newId, node.AgentType, prompt, def.Id, TaskState.Pending, null, DateTimeOffset.UtcNow);
                        await _taskStore.CreateAsync(record, cancellationToken);
                        await _store.SetNodeTaskMappingAsync(def.Id, node.Id, newId, cancellationToken);
                        continue;
                    }

                    var rec = new TaskRecord(newId, node.AgentType, prompt, def.Id, TaskState.Queued, null, DateTimeOffset.UtcNow);
                    await _taskStore.CreateAsync(rec, cancellationToken);
                    await _store.SetNodeTaskMappingAsync(def.Id, node.Id, newId, cancellationToken);
                    var payload = System.Text.Json.JsonSerializer.Serialize(new { Id = newId });
                    await _queue.EnqueueAsync("tasks", payload, cancellationToken);
                }
            }
        }

        /// <summary>
        /// Build an enriched prompt that includes outputs from all predecessor nodes.
        /// This enables true output chaining — downstream agents receive upstream results.
        /// </summary>
        private async Task<string> BuildEnrichedPromptAsync(
            WorkflowNode node,
            WorkflowDefinition def,
            string workflowId,
            CancellationToken cancellationToken)
        {
            var incomingEdges = def.Edges.Where(e => e.ToNodeId == node.Id).ToList();
            if (incomingEdges.Count == 0)
                return node.PromptTemplate;

            var contextParts = new System.Collections.Generic.List<string>();
            foreach (var inc in incomingEdges)
            {
                var predNode = def.Nodes.Find(n => n.Id == inc.FromNodeId);
                var predTaskId = await _store.GetTaskIdForNodeAsync(workflowId, inc.FromNodeId, cancellationToken);
                if (string.IsNullOrEmpty(predTaskId)) continue;

                var predTask = await _taskStore.GetAsync(predTaskId, cancellationToken);
                if (predTask?.ResultJson == null) continue;

                // Extract the Output field from the result JSON
                var output = ExtractOutput(predTask.ResultJson);
                if (!string.IsNullOrEmpty(output))
                {
                    var label = predNode?.Id ?? inc.FromNodeId;
                    contextParts.Add($"[Output from '{label}']:\n{output}");
                }
            }

            if (contextParts.Count == 0)
                return node.PromptTemplate;

            var context = string.Join("\n\n", contextParts);
            return $"{context}\n\n---\n\n{node.PromptTemplate}";
        }

        /// <summary>
        /// Extract the Output string from a task result JSON.
        /// Handles both {"Output":"..."} and plain text results.
        /// </summary>
        private static string ExtractOutput(string resultJson)
        {
            if (string.IsNullOrEmpty(resultJson)) return null;
            try
            {
                using var doc = System.Text.Json.JsonDocument.Parse(resultJson);
                if (doc.RootElement.TryGetProperty("Output", out var outputEl))
                    return outputEl.GetString();
                if (doc.RootElement.TryGetProperty("output", out var outputLower))
                    return outputLower.GetString();
            }
            catch
            {
                // Not valid JSON — return as-is
                return resultJson;
            }
            return resultJson;
        }
    }
}
