Dashboard & Metrics Endpoints

Available endpoints (development):
- /metrics - Prometheus scrape endpoint (prometheus-net)
- /dashboard/agents/concurrency - JSON showing per-agent concurrency limits and currently used semaphores
- /dashboard/summary - Aggregated summary (queue lengths, recent failures, worker count)

Recommendations to extend the dashboard:
1. Add queue-specific metrics: backlog, oldest-message-age, DLQ-count.
2. Expose workflow-level KPIs: running workflows, failed workflows, average node latency.
3. Add alert rules (Prometheus Alertmanager): queue-backlog > 1000 for >5m; failed-tasks-rate > 1%.

Implementation notes:
- MetricsRegistry exposes counters/gauges used by the runtime; read from there to populate /dashboard/agents/concurrency.
- For production, run the Prometheus scrape endpoint behind authentication or in a private network.
