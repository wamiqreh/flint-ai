using System.Threading.Tasks;
using Xunit;
using Orchestrator.Infrastructure.TaskStore;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskLifecycle;
using Orchestrator.Core.TaskLifecycle;
using Orchestrator.Core.Agents;

namespace Orchestrator.Core.Tests
{
    public class TaskLifecycleTests
    {
        [Fact]
        public async Task EngineProcessesDummyTask()
        {
            var store = new InMemoryTaskStore();
            var queue = new RedisQueueAdapter();
            var registry = new AgentRegistry();
            registry.Register("dummy", () => new Orchestrator.Core.Agents.DummyAgent());
            var engine = new TaskLifecycleEngine(store, queue, registry);

            var task = new TaskRecord("t1", "dummy", "say hello", null, TaskState.Pending, null, default);
            await engine.EnqueueTaskAsync(task);

            // process should not throw
            await engine.ProcessNextAsync();

            var rec = await store.GetAsync("t1");
            Assert.NotNull(rec);
            Assert.Equal(TaskState.Succeeded, rec.State);
            Assert.NotNull(rec.ResultJson);
        }
    }
}




