using System;
using System.Threading.Tasks;
using Orchestrator.Infrastructure.Workflow.WorkflowStore;
using Orchestrator.Core.Workflow;
using Xunit;

namespace Orchestrator.Integration.Tests
{
    public class PostgresWorkflowStoreTests
    {
        [Fact]
        public async Task CreateAndRetrieveWorkflowDefinitionAndMappings_WhenConnectionPresent()
        {
            var conn = Environment.GetEnvironmentVariable("POSTGRES_CONNECTION");
            if (string.IsNullOrEmpty(conn))
            {
                // No Postgres available in CI; consider this test skipped.
                return;
            }

            var store = new PostgresWorkflowStore(conn);
            var def = new WorkflowDefinition { Id = "pg-wf-1" };
            def.Nodes.Add(new WorkflowNode("n1", "test", "p1"));
            def.Nodes.Add(new WorkflowNode("n2", "test", "p2"));
            def.Edges.Add(new WorkflowEdge("n1", "n2"));

            await store.CreateAsync(def);
            var loaded = await store.GetAsync(def.Id);
            Assert.NotNull(loaded);
            Assert.Equal(2, loaded.Nodes.Count);

            await store.SetNodeTaskMappingAsync(def.Id, "n1", "task-123");
            var t = await store.GetTaskIdForNodeAsync(def.Id, "n1");
            Assert.Equal("task-123", t);

            var n = await store.GetNodeIdForTaskAsync(def.Id, "task-123");
            Assert.Equal("n1", n);
        }
    }
}




