using System.Threading;
using System.Threading.Tasks;


namespace Orchestrator.Core.Queue
{
    public interface IQueueAdapter
    {
        string Name { get; }
        Task EnqueueAsync(string queueName, string payload, CancellationToken cancellationToken = default);
        Task<(string MessageId, string Payload)> DequeueAsync(string queueName, CancellationToken cancellationToken = default);
        Task AckAsync(string queueName, string messageId, CancellationToken cancellationToken = default);
        Task NackAsync(string queueName, string messageId, CancellationToken cancellationToken = default);
        Task<long> GetLengthAsync(string queueName, CancellationToken cancellationToken = default);
    }
}
