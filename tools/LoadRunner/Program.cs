using System;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskStore;
using Orchestrator.Core.Agents;
using Orchestrator.Infrastructure.TaskLifecycle;
using Orchestrator.Infrastructure.Workflow.WorkflowStore;
using Orchestrator.Core.TaskLifecycle;
using Orchestrator.Infrastructure.Workflow;

class Program
{
    static async Task Main(string[] args)
    {
        int count = args.Length > 0 ? int.Parse(args[0]) : 100;
        int workers = args.Length > 1 ? int.Parse(args[1]) : Math.Max(2, Environment.ProcessorCount / 2);
        int delayMs = args.Length > 2 ? int.Parse(args[2]) : 1; // delay between worker loops
        int maxDurationSec = args.Length > 3 ? int.Parse(args[3]) : 30; // max run time for stress test

        Console.WriteLine($"Load runner: submitting {count} tasks using in-memory stack | workers={workers} delay={delayMs}ms maxDuration={maxDurationSec}s");

        var queue = new InMemoryQueueAdapter();
        var store = new InMemoryTaskStore();
        var wfStore = new InMemoryWorkflowStore();
        var registry = new AgentRegistry();
        registry.Register("dummy", () => new DummyAgent());
        var concurrencyMgr = new AgentConcurrencyManager();
        var wfEngine = new WorkflowEngine(wfStore, queue, store);
        var engine = new TaskLifecycleEngine(store, queue, registry, concurrencyMgr, wfEngine);

        // submit tasks
        for (int i = 0; i < count; i++)
        {
            var id = Guid.NewGuid().ToString();
            var rec = new TaskRecord(id, "dummy", $"payload {i}", null, TaskState.Queued, null, DateTimeOffset.UtcNow);
            await engine.EnqueueTaskAsync(rec);
        }

        int processed = 0;
        var sw = Stopwatch.StartNew();

        // start workers
        var cts = new CancellationTokenSource(TimeSpan.FromSeconds(maxDurationSec));
        var tasks = Enumerable.Range(0, workers).Select(_ => Task.Run(async () =>
        {
            while (!cts.Token.IsCancellationRequested)
            {
                try
                {
                    await engine.ProcessNextAsync(cts.Token);
                    Interlocked.Increment(ref processed);
                    await Task.Delay(delayMs, cts.Token);
                }
                catch (OperationCanceledException) { break; }
                catch (Exception ex) { Console.WriteLine($"Worker error: {ex.Message}"); }
            }
        }, cts.Token)).ToArray();

        // wait until queue empty or time limit
        while ((await queue.GetLengthAsync("tasks") > 0) && !cts.IsCancellationRequested)
        {
            await Task.Delay(100);
        }

        // allow in-flight and cancel workers
        await Task.Delay(500);
        cts.Cancel();
        await Task.WhenAll(tasks);
        sw.Stop();
        Console.WriteLine($"Submitted: {count}, Processed (approx): {processed}, Time: {sw.ElapsedMilliseconds}ms");
        Environment.Exit(0);
    }
}


