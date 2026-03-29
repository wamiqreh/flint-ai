using System;
using System.Threading;
using System.Threading.Tasks;
using Xunit;
using Orchestrator.Infrastructure.TaskStore;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskLifecycle;
using Orchestrator.Core.Agents;
using Orchestrator.Core;
nnnamespace Orchestrator.Integration.Tests
{
    public class TaskLifecycleEngineE2ETests
    {
        [Fact]
        public async Task LifecycleHonorsAdapterRetryAfter()
        {
            // Arrange: create in-memory store, queue, registry with a Copilot agent that uses a test adapter returning 429 then 200
            var store = new InMemoryTaskStore();
            var queue = new InMemoryQueueAdapter();
            var registry = new AgentRegistry();
            var concurrency = new Orchestrator.Infrastructure.TaskLifecycle.AgentConcurrencyManager();
n            // create a fake adapter via CopilotSdkAdapter with handler that returns 429 first (Retry-After 1s), then 200
            var handler = new TestHttpMessageHandler(new[] { (429, "1"), (200, "e2e-result") });
            var http = new System.Net.Http.HttpClient(handler);
            var copilotAdapter = new CopilotSdkAdapter("test-key", "https://api.test", http);
n            // Create a CopilotAgent that uses the adapter via reflection (since constructor wiring is internal here)
            var agent = new TestableCopilotAgent(copilotAdapter);
            registry.Register("copilot", () => agent);
n            var engine = new TaskLifecycleEngine(store, queue, registry, concurrency);
n            // Enqueue a task
            var taskId = Guid.NewGuid().ToString();
            var record = new TaskRecord(taskId, "copilot", "prompt e2e", null, TaskState.Queued, DateTimeOffset.UtcNow, null);
            await engine.EnqueueTaskAsync(record);
n            // Act: process next (should call adapter, get 429, wait ~1s, then succeed)
            var sw = System.Diagnostics.Stopwatch.StartNew();
            await engine.ProcessNextAsync(CancellationToken.None);
            sw.Stop();
n            // Assert
            Assert.True(sw.Elapsed.TotalSeconds >= 1, $"Elapsed {sw.Elapsed.TotalSeconds} should be >= 1 due to Retry-After");
            var saved = await store.GetAsync(taskId);
            Assert.Equal(TaskState.Succeeded, saved.State);
            Assert.Contains("e2e-result", saved.ResultJson);
        }
    }
n    // Helper: lightweight test HTTP handler that returns a sequence of responses; for 429 includes Retry-After header value
    internal class TestHttpMessageHandler : System.Net.Http.HttpMessageHandler
    {
        private readonly (int status, string body)[] _seq;
        private int _index = 0;
        public TestHttpMessageHandler((int status, string body)[] seq) { _seq = seq; }
        protected override Task<System.Net.Http.HttpResponseMessage> SendAsync(System.Net.Http.HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var idx = System.Threading.Interlocked.Increment(ref _index) - 1;
            var item = _seq[Math.Min(idx, _seq.Length - 1)];
            var resp = new System.Net.Http.HttpResponseMessage((System.Net.HttpStatusCode)item.status);
            if (item.status == 429) resp.Headers.TryAddWithoutValidation("Retry-After", item.body);
            else resp.Content = new System.Net.Http.StringContent(item.body);
            return Task.FromResult(resp);
        }
    }
n    // TestableCopilotAgent: wraps adapter and implements IAgent
    internal class TestableCopilotAgent : IAgent
    {
        private readonly CopilotSdkAdapter _adapter;
        public TestableCopilotAgent(CopilotSdkAdapter adapter) { _adapter = adapter; }
        public string AgentType => "copilot";
        public async Task<AgentResult> ExecuteAsync(TaskDefinition task, AgentContext context, CancellationToken cancellationToken)
        {
            try
            {
                var text = await _adapter.SendPromptAsync(task.Prompt, cancellationToken);
                return new AgentResult(task.Id, true, text);
            }
            catch (AgentRetryAfterException)
            {
                throw;
            }
            catch (Exception ex)
            {
                return new AgentResult(task.Id, false, null, ex.ToString());
            }
        }
    }
}


