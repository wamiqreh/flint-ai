using System;
using System.IO;
using System.Threading.Tasks;
using Orchestrator.Infrastructure.Migrations;
using Orchestrator.Infrastructure.Workflow.WorkflowStore;
using Orchestrator.Infrastructure.Workflow;
using Orchestrator.Core.Workflow;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskStore;
using Xunit;

namespace Orchestrator.Integration.Tests
{
    public class WorkflowResumePostgresTests
    {
        [Fact]
        public async Task WorkflowEngine_ResumesAndEnqueuesNextNode_WhenPostgresAvailable()
        {
            var conn = Environment.GetEnvironmentVariable("POSTGRES_CONNECTION");
            if (string.IsNullOrEmpty(conn))
            {
                // Skip when Postgres is not configured in CI/local env
                return;
            }

            // locate migrations folder (where V1__create_workflow_tables.sql lives)
            var migrationsFolder = Path.Combine(Environment.CurrentDirectory, "src", "Orchestrator.Infrastructure", "Workflow");
            await MigrationRunner.RunMigrationsAsync(conn, migrationsFolder);

            var store = new PostgresWorkflowStore(conn);
            var def = new WorkflowDefinition { Id = "resume-wf-1" };
            def.Nodes.Add(new WorkflowNode("n1", "test", "p1"));
            def.Nodes.Add(new WorkflowNode("n2", "test", "p2"));
            def.Edges.Add(new WorkflowEdge("n1", "n2"));

            await store.CreateAsync(def);

            var queue = new InMemoryQueueAdapter();
            var taskStore = new InMemoryTaskStore();
            var engine = new WorkflowEngine(store, queue, taskStore);

            // simulate that node n1 was executed and mapped to task-1
            await store.SetNodeTaskMappingAsync(def.Id, "n1", "task-1");

            // now simulate completion of task-1
            await engine.OnTaskCompletedAsync("task-1", def.Id);

            var len = await queue.GetLengthAsync("tasks");
            Assert.True(len >= 1, "Expected next node enqueued after task completion");
        }
    }
}




