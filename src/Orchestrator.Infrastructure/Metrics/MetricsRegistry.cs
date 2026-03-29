using Prometheus;


namespace Orchestrator.Infrastructure.Metrics
{
    public static class MetricsRegistry
    {
        public static readonly Counter TasksProcessed = Prometheus.Metrics.CreateCounter("orchestrator_tasks_processed_total", "Total tasks processed");
        public static readonly Counter TasksSucceeded = Prometheus.Metrics.CreateCounter("orchestrator_tasks_succeeded_total", "Tasks succeeded");
        public static readonly Counter TasksFailed = Prometheus.Metrics.CreateCounter("orchestrator_tasks_failed_total", "Tasks failed");
        public static readonly Gauge QueueLength = Prometheus.Metrics.CreateGauge("orchestrator_queue_length", "Queue length");

        // Per-agent concurrency metrics: configured limit and current used
        public static readonly Gauge AgentConcurrencyLimit = Prometheus.Metrics.CreateGauge("orchestrator_agent_concurrency_limit", "Configured concurrency limit for agent type", new[] { "agent" });
        public static readonly Gauge AgentConcurrencyUsed = Prometheus.Metrics.CreateGauge("orchestrator_agent_concurrency_used", "Current used concurrency for agent type", new[] { "agent" });

        // DLQ and pending counts per queue
        public static readonly Gauge AgentDlqLength = Prometheus.Metrics.CreateGauge("orchestrator_queue_dlq_length", "Dead-letter queue length for stream", new[] { "queue" });
        public static readonly Gauge AgentPendingCount = Prometheus.Metrics.CreateGauge("orchestrator_queue_pending_count", "Pending entries count for stream consumer group", new[] { "queue" });

        // Reclaimed entries counter
        public static readonly Counter ReclaimedEntries = Prometheus.Metrics.CreateCounter("orchestrator_reclaimed_entries_total", "Total reclaimed entries from pending state");
    }
}
