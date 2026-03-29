using System;
using System.Collections.Concurrent;
using System.Threading;


namespace Orchestrator.Infrastructure.TaskLifecycle
{
    // Manages per-agent concurrency semaphores. Concurrency can be configured via env vars:
    // DEFAULT_AGENT_CONCURRENCY (int) or per-agent CONCURRENCY_{AGENTTYPE} (e.g., CONCURRENCY_COPILOT=3)
    public class AgentConcurrencyManager
    {
        private readonly ConcurrentDictionary<string, SemaphoreSlim> _semaphores = new();
        private readonly ConcurrentDictionary<string, int> _limits = new();
        private readonly int _defaultConcurrency;

        public AgentConcurrencyManager()
        {
            var def = Environment.GetEnvironmentVariable("DEFAULT_AGENT_CONCURRENCY");
            if (!int.TryParse(def, out _defaultConcurrency))
            {
                _defaultConcurrency = 2;
            }
        }

        public SemaphoreSlim GetSemaphore(string agentType)
        {
            var key = (agentType ?? "default").ToLowerInvariant();
            return _semaphores.GetOrAdd(key, _ =>
            {
                var envName = $"CONCURRENCY_{key.ToUpperInvariant()}";
                var sval = Environment.GetEnvironmentVariable(envName);
                int concurrency;
                if (int.TryParse(sval, out var c) && c > 0)
                {
                    concurrency = c;
                }
                else
                {
                    concurrency = _defaultConcurrency;
                }
                _limits[key] = concurrency;
                // set metrics for limit and initial used (0)
                try
                {
                    Orchestrator.Infrastructure.Metrics.MetricsRegistry.AgentConcurrencyLimit.WithLabels(key).Set(concurrency);
                    Orchestrator.Infrastructure.Metrics.MetricsRegistry.AgentConcurrencyUsed.WithLabels(key).Set(0);
                }
                catch { }
                return new SemaphoreSlim(concurrency);
            });
        }

        public int GetConcurrencyLimit(string agentType)
        {
            var key = (agentType ?? "default").ToLowerInvariant();
            if (_limits.TryGetValue(key, out var v)) return v;
            return _defaultConcurrency;
        }

        // Return approximate current used count for an agent type (limit - current semaphore count)
        public int GetCurrentUsage(string agentType)
        {
            var key = (agentType ?? "default").ToLowerInvariant();
            if (_semaphores.TryGetValue(key, out var sem))
            {
                var limit = GetConcurrencyLimit(agentType);
                try
                {
                    var current = sem.CurrentCount; // available slots
                    return Math.Max(0, limit - current);
                }
                catch
                {
                    return 0;
                }
            }
            return 0;
        }
    }
}
