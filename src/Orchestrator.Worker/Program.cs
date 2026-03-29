using Orchestrator.Core.Agents;
using Orchestrator.Core.Queue;
using Orchestrator.Core.TaskLifecycle;
using Orchestrator.Infrastructure.Migrations;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskLifecycle;
using Orchestrator.Infrastructure.TaskStore;

namespace Orchestrator.Worker;

internal class Program
{
    private static async Task Main(string[] args)
    {
        var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            cts.Cancel();
        };

        Console.WriteLine("Worker starting. Press Ctrl+C to stop.");

        var metricServer = new Prometheus.MetricServer(hostname: "localhost", port: 1234);
        metricServer.Start();

        ITaskStore store;
        var conn = Environment.GetEnvironmentVariable("POSTGRES_CONNECTION");
        if (!string.IsNullOrEmpty(conn))
        {
            Console.WriteLine("[Worker] POSTGRES_CONNECTION found, running migrations and using PostgresTaskStore.");
            var migrationsFolder = Path.Combine(AppContext.BaseDirectory, "Migrations");
            await MigrationRunner.RunMigrationsAsync(conn, migrationsFolder);
            store = new PostgresTaskStore(conn);
        }
        else
        {
            store = new InMemoryTaskStore();
        }

        var queue = new RedisQueueAdapter();
        var registry = new AgentRegistry();
        registry.Register("dummy", () => new DummyAgent());
        var concurrencyManager = new AgentConcurrencyManager();
        var engine = new TaskLifecycleEngine(store, queue, registry, concurrencyManager);

        try
        {
            var reaper = new BackgroundPendingReaper(queue, "tasks", intervalMs: 30000, batchSize: 10);
            reaper.Start(cts.Token);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[Worker] failed to start reaper: {ex.Message}");
        }

        while (!cts.Token.IsCancellationRequested)
        {
            await engine.ProcessNextAsync(cts.Token);
            await Task.Delay(200, cts.Token);
        }

        metricServer.Stop();
        Console.WriteLine("Worker stopping.");
    }
}
