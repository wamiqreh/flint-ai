using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Dapper;
using Npgsql;
using Orchestrator.Core.TaskLifecycle;

namespace Orchestrator.Infrastructure.TaskStore
{
    public class PostgresTaskStore : ITaskStore, IDisposable
    {
        private readonly string _connectionString;

        public PostgresTaskStore(string connectionString)
        {
            _connectionString = connectionString ?? throw new ArgumentNullException(nameof(connectionString));
        }

        private NpgsqlConnection GetConn() => new NpgsqlConnection(_connectionString);

        public async Task CreateAsync(TaskRecord task, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            await conn.ExecuteAsync(@"INSERT INTO tasks(id, agent_type, prompt, workflow_id, state, result_json, created_at)
VALUES(@Id,@AgentType,@Prompt,@WorkflowId,@State,@ResultJson,@CreatedAt)", new
            {
                Id = task.Id,
                AgentType = task.AgentType,
                Prompt = task.Prompt,
                WorkflowId = task.WorkflowId,
                State = task.State.ToString(),
                ResultJson = task.ResultJson,
                CreatedAt = task.CreatedAt == default ? DateTimeOffset.UtcNow : task.CreatedAt
            });
        }

        public async Task<TaskRecord> GetAsync(string id, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            var row = await conn.QuerySingleOrDefaultAsync(@"SELECT id, agent_type, prompt, workflow_id, state, result_json, created_at FROM tasks WHERE id = @id", new { id });
            if (row == null) return null;
            return new TaskRecord((string)row.id, (string)row.agent_type, (string)row.prompt, (string)row.workflow_id, Enum.Parse<TaskState>((string)row.state), (string)row.result_json, (DateTimeOffset)row.created_at);
        }

        public async Task UpdateStateAsync(string id, TaskState state, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            await conn.ExecuteAsync("UPDATE tasks SET state=@state WHERE id=@id", new { state = state.ToString(), id });
        }

        public async Task SaveResultAsync(string id, string resultJson, CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            await conn.ExecuteAsync("UPDATE tasks SET result_json=@result WHERE id=@id", new { result = resultJson, id });
        }

        public async Task<IEnumerable<TaskRecord>> ListAsync(CancellationToken cancellationToken = default)
        {
            using var conn = GetConn();
            await conn.OpenAsync(cancellationToken);
            var rows = await conn.QueryAsync(@"SELECT id, agent_type, prompt, workflow_id, state, result_json, created_at FROM tasks");
            var list = new List<TaskRecord>();
            foreach (var row in rows)
            {
                list.Add(new TaskRecord((string)row.id, (string)row.agent_type, (string)row.prompt, (string)row.workflow_id, Enum.Parse<TaskState>((string)row.state), (string)row.result_json, (DateTimeOffset)row.created_at));
            }
            return list;
        }

        public void Dispose() { }
    }
}
