using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.TaskLifecycle;


namespace Orchestrator.Infrastructure.TaskStore
{
    public class InMemoryTaskStore : ITaskStore
    {
        private readonly ConcurrentDictionary<string, TaskRecord> _store = new();

        public Task CreateAsync(TaskRecord task, CancellationToken cancellationToken = default)
        {
            var record = task with { CreatedAt = task.CreatedAt == default ? DateTimeOffset.UtcNow : task.CreatedAt };
            _store[task.Id] = record;
            return Task.CompletedTask;
        }

        public Task<TaskRecord> GetAsync(string id, CancellationToken cancellationToken = default)
        {
            _store.TryGetValue(id, out var record);
            return Task.FromResult(record);
        }

        public Task UpdateStateAsync(string id, TaskState state, CancellationToken cancellationToken = default)
        {
            if (_store.TryGetValue(id, out var rec))
            {
                _store[id] = rec with { State = state };
            }
            return Task.CompletedTask;
        }

        public Task SaveResultAsync(string id, string resultJson, CancellationToken cancellationToken = default)
        {
            if (_store.TryGetValue(id, out var rec))
            {
                _store[id] = rec with { ResultJson = resultJson };
            }
            return Task.CompletedTask;
        }

        public Task<IEnumerable<TaskRecord>> ListAsync(CancellationToken cancellationToken = default)
        {
            return Task.FromResult((IEnumerable<TaskRecord>)_store.Values);
        }
    }
}
