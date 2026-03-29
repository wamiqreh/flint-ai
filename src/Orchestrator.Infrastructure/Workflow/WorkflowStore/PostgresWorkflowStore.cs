using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Dapper;
using Npgsql;
using Orchestrator.Core.Workflow;

namespace Orchestrator.Infrastructure.Workflow.WorkflowStore
{
    public class PostgresWorkflowStore : IWorkflowStore, IDisposable
    {
        private readonly string _connectionString;
        private static readonly JsonSerializerOptions s_jsonOpts = new() { PropertyNameCaseInsensitive = true };

        public PostgresWorkflowStore(string connectionString)
        {
            _connectionString = connectionString ?? throw new ArgumentNullException(nameof(connectionString));
        }

        private NpgsqlConnection GetConn() => new NpgsqlConnection(_connectionString);

        public async Task CreateAsync(WorkflowDefinition def, CancellationToken cancellationToken = default)
        {
            var json = JsonSerializer.Serialize(def);
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            await conn.ExecuteAsync(
                @"INSERT INTO workflow_definitions(id, definition) VALUES(@id, @def)
                  ON CONFLICT(id) DO UPDATE SET definition = @def",
                new { id = def.Id, def = json });
        }

        public async Task<WorkflowDefinition> GetAsync(string id, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            var json = await conn.QuerySingleOrDefaultAsync<string>(
                "SELECT definition FROM workflow_definitions WHERE id = @id", new { id });
            if (json == null) return null;
            return JsonSerializer.Deserialize<WorkflowDefinition>(json, s_jsonOpts);
        }

        public async Task<IEnumerable<WorkflowDefinition>> ListAsync(CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            var rows = await conn.QueryAsync<string>("SELECT definition FROM workflow_definitions");
            var list = new List<WorkflowDefinition>();
            foreach (var json in rows)
            {
                var def = JsonSerializer.Deserialize<WorkflowDefinition>(json, s_jsonOpts);
                if (def != null) list.Add(def);
            }
            return list;
        }

        public async Task SetNodeTaskMappingAsync(string workflowId, string nodeId, string taskId, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            await conn.ExecuteAsync(
                @"INSERT INTO workflow_node_tasks(workflow_id, node_id, task_id) VALUES(@wf, @node, @task)
                  ON CONFLICT(workflow_id, node_id) DO UPDATE SET task_id = @task",
                new { wf = workflowId, node = nodeId, task = taskId });
        }

        public async Task<string> GetTaskIdForNodeAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            return await conn.QuerySingleOrDefaultAsync<string>(
                "SELECT task_id FROM workflow_node_tasks WHERE workflow_id = @wf AND node_id = @node",
                new { wf = workflowId, node = nodeId });
        }

        public async Task<string> GetNodeIdForTaskAsync(string workflowId, string taskId, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            return await conn.QuerySingleOrDefaultAsync<string>(
                "SELECT node_id FROM workflow_node_tasks WHERE workflow_id = @wf AND task_id = @task",
                new { wf = workflowId, task = taskId });
        }

        public async Task<int> GetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            return await conn.QuerySingleOrDefaultAsync<int>(
                "SELECT COALESCE(attempt_count, 0) FROM workflow_node_attempts WHERE workflow_id = @wf AND node_id = @node",
                new { wf = workflowId, node = nodeId });
        }

        public async Task<int> IncrementAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            return await conn.QuerySingleAsync<int>(
                @"INSERT INTO workflow_node_attempts(workflow_id, node_id, attempt_count) VALUES(@wf, @node, 1)
                  ON CONFLICT(workflow_id, node_id) DO UPDATE SET attempt_count = workflow_node_attempts.attempt_count + 1
                  RETURNING attempt_count",
                new { wf = workflowId, node = nodeId });
        }

        public async Task ResetAttemptCountAsync(string workflowId, string nodeId, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            await conn.ExecuteAsync(
                @"INSERT INTO workflow_node_attempts(workflow_id, node_id, attempt_count) VALUES(@wf, @node, 0)
                  ON CONFLICT(workflow_id, node_id) DO UPDATE SET attempt_count = 0",
                new { wf = workflowId, node = nodeId });
        }

        public void Dispose() { }
    }
}
