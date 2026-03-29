using System;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Infrastructure.Queue
{
    // Background reaper that periodically calls ReclaimPendingAsync on the RedisQueueAdapter
    public class BackgroundPendingReaper
    {
        private readonly RedisQueueAdapter _adapter;
        private readonly string _queueName;
        private readonly int _intervalMs;
        private readonly int _batchSize;

        public BackgroundPendingReaper(RedisQueueAdapter adapter, string queueName = "tasks", int intervalMs = 30000, int batchSize = 10)
        {
            _adapter = adapter ?? throw new ArgumentNullException(nameof(adapter));
            _queueName = queueName;
            _intervalMs = intervalMs;
            _batchSize = batchSize;
        }

        public void Start(CancellationToken token)
        {
            _ = RunAsync(token);
        }

        private async Task RunAsync(CancellationToken token)
        {
            Console.WriteLine($"[BackgroundPendingReaper] starting for queue {_queueName}, interval {_intervalMs}ms, batch {_batchSize}");
            int consecutiveErrors = 0;
            while (!token.IsCancellationRequested)
            {
                try
                {
                    var reclaimed = await _adapter.ReclaimPendingAsync(_queueName, _batchSize, token);
                    if (reclaimed > 0)
                    {
                        Console.WriteLine($"[BackgroundPendingReaper] reclaimed {reclaimed} entries for {_queueName}");
                        Orchestrator.Infrastructure.Metrics.MetricsRegistry.ReclaimedEntries.Inc(reclaimed);
                    }
                    consecutiveErrors = 0;
                }
                catch (Exception ex)
                {
                    consecutiveErrors++;
                    Console.WriteLine($"[BackgroundPendingReaper] error: {ex.Message}");
                }

                try
                {
                    var delay = Math.Min(_intervalMs * (1 + consecutiveErrors), 60000);
                    await Task.Delay(delay, token);
                }
                catch (TaskCanceledException) { break; }
            }

            Console.WriteLine("[BackgroundPendingReaper] stopping");
        }
    }
}
