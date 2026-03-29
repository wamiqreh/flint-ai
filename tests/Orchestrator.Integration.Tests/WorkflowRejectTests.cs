using System.Threading.Tasks;
using Xunit;
using Orchestrator.Infrastructure.Workflow.WorkflowStore;
using Orchestrator.Infrastructure.Workflow;
using Orchestrator.Core.Workflow;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskStore;
using Orchestrator.Core.TaskLifecycle;

namespace Orchestrator.Integration.Tests
{
    public class WorkflowRejectTests
    {
        [Fact]
        public async Task RejectNode_marksTaskDeadLetter()
        {
            var store = new InMemoryWorkflowStore();
            var queue = new InMemoryQueueAdapter();
            var taskStore = new InMemoryTaskStore();

            var def = new WorkflowDefinition { Id = "reject-wf-1" };
            def.Nodes.Add(new WorkflowNode("n1", "test", "p1", MaxRetries: 1, DeadLetterOnFailure: true, HumanApproval: true));
            await store.CreateAsync(def);

            var engine = new WorkflowEngine(store, queue, taskStore);

            // create an initial task mapping for n1
            await store.SetNodeTaskMappingAsync(def.Id, "n1", "task-1");
            await taskStore.CreateAsync(new TaskRecord("task-1", "test", "p1", def.Id, TaskState.Running, null, System.DateTimeOffset.UtcNow));

            // reject the node
            await engine.RejectNodeAsync(def.Id, "n1");

            var t = await taskStore.GetAsync("task-1");
            Assert.Equal(TaskState.DeadLetter, t.State);
        }
    }
}




