using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.Workflow;

namespace Orchestrator.Infrastructure.Workflow.WorkflowStore
{
    public class InMemoryWorkflowStore : IWorkflowStore
    {
        private readonly ConcurrentDictionary<string, WorkflowDefinition> _defs = new();
        private readonly ConcurrentDictionary<string, string> _nodeToTask = new(); // key: workflowId|nodeId -> taskId
        private readonly ConcurrentDictionary<string, string> _taskToNode = new(); // key: workflowId|taskId -> nodeId
        private readonly ConcurrentDictionary<string, int> _nodeAttempts = new();

        private static string KeyForNode(string workflowId, string nodeId) => $"{workflowId}|node|{nodeId}";
        private static string KeyForTask(string workflowId, string taskId) => $"{workflowId}|task|{taskId}";
        private static string KeyForAttempt(string workflowId, string nodeId) => $"{workflowId}|attempt|{nodeId}";

        public Task CreateAsync(WorkflowDefinition def, CancellationToken cancellationToken = default)
        {
            _defs[def.Id] = def;
            return Task.CompletedTask;
        }

        public Task<WorkflowDefinition> GetAsync(string id, CancellationToken cancellationToken = default)
        {
            _defs.TryGetValue(id, out var def);
            return Task.FromResult(def!);
        }

        public Task SetNodeTaskMappingAsync(string workflowId, string nodeId, string taskId, CancellationToken cancellationToken = default)
        {
            _nodeToTask[KeyForNode(workflowId, nodeId)] = taskId;
            _taskToNode[KeyForTask(workflowId, taskId)] = nodeId;
            return Task.CompletedTask;
        }

        public Task<string> GetTaskIdForNodeAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            _nodeToTask.TryGetValue(KeyForNode(workflowId, nodeId), out var taskId);
            return Task.FromResult(taskId!);
        }

        public Task<string> GetNodeIdForTaskAsync(string workflowId, string taskId, CancellationToken cancellationToken = default)
        {
            _taskToNode.TryGetValue(KeyForTask(workflowId, taskId), out var nodeId);
            return Task.FromResult(nodeId!);
        }

        public Task<int> GetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            _nodeAttempts.TryGetValue(KeyForAttempt(workflowId, nodeId), out var count);
            return Task.FromResult(count);
        }

        public Task<int> IncrementAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            var key = KeyForAttempt(workflowId, nodeId);
            var val = _nodeAttempts.AddOrUpdate(key, 1, (_, old) => old + 1);
            return Task.FromResult(val);
        }

        public Task ResetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            _nodeAttempts[KeyForAttempt(workflowId, nodeId)] = 0;
            return Task.CompletedTask;
        }

        public Task<IEnumerable<WorkflowDefinition>> ListAsync(CancellationToken cancellationToken = default)
        {
            var list = _defs.Values.ToList();
            return Task.FromResult((IEnumerable<WorkflowDefinition>)list);
        }
    }
}


