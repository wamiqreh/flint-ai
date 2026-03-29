using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.Queue;


namespace Orchestrator.Infrastructure.Queue
{
    public class InMemoryQueueAdapter : IQueueAdapter
    {
        private readonly ConcurrentDictionary<string, ConcurrentQueue<(string id, string payload)>> _queues = new();

        public string Name => "inmemory";

        public Task AckAsync(string queueName, string messageId, CancellationToken cancellationToken = default)
        {
            // no-op for in-memory queue
            return Task.CompletedTask;
        }

        public Task EnqueueAsync(string queueName, string payload, CancellationToken cancellationToken = default)
        {
            var q = _queues.GetOrAdd(queueName, _ => new ConcurrentQueue<(string, string)>());
            var id = Guid.NewGuid().ToString();
            q.Enqueue((id, payload));
            return Task.CompletedTask;
        }

        public Task<(string MessageId, string Payload)> DequeueAsync(string queueName, CancellationToken cancellationToken = default)
        {
            var q = _queues.GetOrAdd(queueName, _ => new ConcurrentQueue<(string, string)>());
            if (q.TryDequeue(out var item)) return Task.FromResult((item.id, item.payload));
            return Task.FromResult<(string, string)>((null, null));
        }

        public Task NackAsync(string queueName, string messageId, CancellationToken cancellationToken = default)
        {
            // for in-memory, Nack is no-op
            return Task.CompletedTask;
        }

        public Task<long> GetLengthAsync(string queueName, CancellationToken cancellationToken = default)
        {
            var q = _queues.GetOrAdd(queueName, _ => new ConcurrentQueue<(string, string)>());
            return Task.FromResult((long)q.Count);
        }
    }
}
