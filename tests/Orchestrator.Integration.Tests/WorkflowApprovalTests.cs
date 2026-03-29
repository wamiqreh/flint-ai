using System;
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
    public class WorkflowApprovalTests
    {
        [Fact]
        public async Task ApprovingHumanApprovalNode_enqueuesNewTask()
        {
            var store = new InMemoryWorkflowStore();
            var queue = new InMemoryQueueAdapter();
            var taskStore = new InMemoryTaskStore();

            var def = new WorkflowDefinition { Id = "approval-wf-1" };
            def.Nodes.Add(new WorkflowNode("n1", "test", "p1", MaxRetries: 1, DeadLetterOnFailure: true, HumanApproval: true));
            def.Nodes.Add(new WorkflowNode("n2", "test", "p2"));
            def.Edges.Add(new WorkflowEdge("n1", "n2"));
            await store.CreateAsync(def);

            var engine = new WorkflowEngine(store, queue, taskStore);

            // create an initial task mapping for n1
            await store.SetNodeTaskMappingAsync(def.Id, "n1", "task-1");
            await taskStore.CreateAsync(new TaskRecord("task-1", "test", "p1", def.Id, TaskState.Running, null, DateTimeOffset.UtcNow));

            // simulate failure -> should move to DeadLetter due to HumanApproval
            await engine.OnTaskFailedAsync("task-1", def.Id);
            var t = await taskStore.GetAsync("task-1");
            Assert.Equal(TaskState.DeadLetter, t.State);

            // approve the node and expect a new queued task to be created and enqueued
            await engine.ApproveNodeAsync(def.Id, "n1");
            var len = await queue.GetLengthAsync("tasks");
            Assert.True(len >= 1, "Expected new task enqueued after approval");

            // fetch mapping for node
            var newTaskId = await store.GetTaskIdForNodeAsync(def.Id, "n1");
            Assert.False(string.IsNullOrEmpty(newTaskId));
            var newTask = await taskStore.GetAsync(newTaskId);
            Assert.Equal(TaskState.Queued, newTask.State);
        }
    }
}




