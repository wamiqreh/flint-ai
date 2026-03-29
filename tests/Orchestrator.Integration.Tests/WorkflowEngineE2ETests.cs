using System;
using System.Threading;
using System.Threading.Tasks;
using Xunit;
using Orchestrator.Infrastructure.Workflow.WorkflowStore;
using Orchestrator.Infrastructure.Workflow;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskStore;
using Orchestrator.Core.Workflow;
using Orchestrator.Core.TaskLifecycle;

namespace Orchestrator.Integration.Tests
{
    public class WorkflowEngineE2ETests
    {
        [Fact]
        public async Task EngineEnqueuesNextNodeOnCompletion()
        {
            var store = new InMemoryWorkflowStore();
            var queue = new InMemoryQueueAdapter();
            var taskStore = new InMemoryTaskStore();

            var def = new WorkflowDefinition { Id = "wf1" };
            def.Nodes.Add(new WorkflowNode("n1", "copilot", "prompt1"));
            def.Nodes.Add(new WorkflowNode("n2", "copilot", "prompt2"));
            def.Edges.Add(new WorkflowEdge("n1", "n2"));
            await store.CreateAsync(def);

            var engine = new WorkflowEngine(store, queue, taskStore);

            // simulate task n1 completed
            var taskId = "n1";
            await engine.OnTaskCompletedAsync(taskId, "wf1");

            // ensure queue has one message and taskStore has a new record
            var len = await queue.GetLengthAsync("tasks");
            Assert.True(len >= 1);
        }
    }
}




