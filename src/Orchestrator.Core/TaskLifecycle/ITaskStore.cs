using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;


namespace Orchestrator.Core.TaskLifecycle
{
    public interface ITaskStore
    {
        Task CreateAsync(TaskRecord task, CancellationToken cancellationToken = default);
        Task<TaskRecord> GetAsync(string id, CancellationToken cancellationToken = default);
        Task UpdateStateAsync(string id, TaskState state, CancellationToken cancellationToken = default);
        Task SaveResultAsync(string id, string resultJson, CancellationToken cancellationToken = default);
        Task<IEnumerable<TaskRecord>> ListAsync(CancellationToken cancellationToken = default);
    }
}
