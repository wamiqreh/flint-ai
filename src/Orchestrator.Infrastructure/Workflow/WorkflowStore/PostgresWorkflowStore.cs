using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.Workflow;

namespace Orchestrator.Infrastructure.Workflow.WorkflowStore
{
    public class PostgresWorkflowStore : IWorkflowStore
    {
        // Placeholder: minimal in-memory backing for Postgres store to allow builds/tests without DB
        private readonly Dictionary<string, WorkflowDefinition> _defs = new();
        private readonly Dictionary<string, string> _nodeToTask = new();
        private readonly Dictionary<string, string> _taskToNode = new();
        private readonly Dictionary<string, int> _attempts = new();

        public Task CreateAsync(WorkflowDefinition def, CancellationToken cancellationToken = default)
        {
            _defs[def.Id] = def;
            return Task.CompletedTask;
        }

        public Task<WorkflowDefinition> GetAsync(string id, CancellationToken cancellationToken = default)
        {
            _defs.TryGetValue(id, out var def);
            return Task.FromResult(def);
        }

        public Task SetNodeTaskMappingAsync(string workflowId, string nodeId, string taskId, CancellationToken cancellationToken = default)
        {
            _nodeToTask[$"{workflowId}|{nodeId}"] = taskId;
            _taskToNode[$"{workflowId}|{taskId}"] = nodeId;
            return Task.CompletedTask;
        }

        public Task<string> GetTaskIdForNodeAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            _nodeToTask.TryGetValue($"{workflowId}|{nodeId}", out var t);
            return Task.FromResult(t);
        }

        public Task<string> GetNodeIdForTaskAsync(string workflowId, string taskId, CancellationToken cancellationToken = default)
        {
            _taskToNode.TryGetValue($"{workflowId}|{taskId}", out var n);
            return Task.FromResult(n);
        }

        public Task<int> GetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            _attempts.TryGetValue($"{workflowId}|{nodeId}", out var v);
            return Task.FromResult(v);
        }

        public Task<int> IncrementAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            var key = $"{workflowId}|{nodeId}";
            if (!_attempts.ContainsKey(key)) _attempts[key] = 0;
            _attempts[key] = _attempts[key] + 1;
            return Task.FromResult(_attempts[key]);
        }

        public Task ResetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            _attempts[$"{workflowId}|{nodeId}"] = 0;
            return Task.CompletedTask;
        }

        public Task<IEnumerable<WorkflowDefinition>> ListAsync(CancellationToken cancellationToken = default)
        {
            return Task.FromResult((IEnumerable<WorkflowDefinition>)new List<WorkflowDefinition>(_defs.Values));
        }
    }
}
