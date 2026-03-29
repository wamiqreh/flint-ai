using System;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.Queue;
using StackExchange.Redis;
using Orchestrator.Infrastructure.Metrics;


namespace Orchestrator.Infrastructure.Queue
{
    // Redis Streams-based queue adapter using consumer groups with pending-entry reclaim (XAUTOCLAIM).
    public class RedisQueueAdapter : IQueueAdapter
    {
        private readonly string _connectionString;
        private ConnectionMultiplexer _conn;
        private readonly string _groupName;
        private readonly string _consumerName;
        private readonly int _reclaimMinIdleMs;

        public RedisQueueAdapter()
        {
            _connectionString = Environment.GetEnvironmentVariable("REDIS_CONNECTION") ?? "localhost:6379";
            _groupName = Environment.GetEnvironmentVariable("REDIS_CONSUMER_GROUP") ?? "orchestrator-group";
            _consumerName = Environment.GetEnvironmentVariable("REDIS_CONSUMER_NAME") ?? (Environment.MachineName + "-" + Guid.NewGuid().ToString().Substring(0, 6));
            if (!int.TryParse(Environment.GetEnvironmentVariable("REDIS_RECLAIM_MIN_IDLE_MS"), out _reclaimMinIdleMs)) _reclaimMinIdleMs = 60000;
        }

        private void EnsureConnected()
        {
            if (_conn == null || !_conn.IsConnected)
            {
                _conn = ConnectionMultiplexer.Connect(_connectionString);
            }
        }

        public string Name => "redis-streams";

        private IDatabase Db
        {
            get
            {
                EnsureConnected();
                return _conn.GetDatabase();
            }
        }

        public async Task EnqueueAsync(string queueName, string payload, CancellationToken cancellationToken = default)
        {
            await Db.ExecuteAsync("XADD", queueName, "*", "payload", payload).ConfigureAwait(false);
        }

        private async Task EnsureGroupExistsAsync(string queueName)
        {
            try
            {
                await Db.ExecuteAsync("XGROUP", "CREATE", queueName, _groupName, "$", "MKSTREAM").ConfigureAwait(false);
            }
            catch (RedisServerException ex)
            {
                if (!ex.Message.Contains("BUSYGROUP")) throw;
            }
        }

        public async Task<(string MessageId, string Payload)> DequeueAsync(string queueName, CancellationToken cancellationToken = default)
        {
            await EnsureGroupExistsAsync(queueName).ConfigureAwait(false);

            // First, attempt to reclaim old pending entries (XAUTOCLAIM)
            try
            {
                var reclaimRes = await Db.ExecuteAsync("XAUTOCLAIM", queueName, _groupName, _consumerName, _reclaimMinIdleMs.ToString(), "0-0", "COUNT", "1").ConfigureAwait(false);
                if (!reclaimRes.IsNull)
                {
                    var reclaimOuter = (RedisResult[])reclaimRes;
                    if (reclaimOuter.Length >= 2)
                    {
                        var entries = (RedisResult[])reclaimOuter[1];
                        if (entries.Length > 0)
                        {
                            var entry = (RedisResult[])entries[0];
                            var id = (string)entry[0];
                            var fields = (RedisResult[])entry[1];
                            string payload = null;
                            for (int i = 0; i < fields.Length; i += 2)
                            {
                                var fname = (string)fields[i];
                                var fval = (string)fields[i + 1];
                                if (fname == "payload") { payload = fval; break; }
                            }
                            return (id, payload);
                        }
                    }
                }
            }
            catch { /* ignore, fallback to normal read */ }

            // Fall back to reading new messages from the stream
            var res = await Db.ExecuteAsync("XREADGROUP", "GROUP", _groupName, _consumerName, "COUNT", "1", "STREAMS", queueName, ">").ConfigureAwait(false);
            if (res.IsNull) return (null, null);

            try
            {
                var outer = (RedisResult[])res;
                if (outer.Length == 0) return (null, null);
                var streamRes = (RedisResult[])outer[0];
                if (streamRes.Length < 2) return (null, null);
                var entries = (RedisResult[])streamRes[1];
                if (entries.Length == 0) return (null, null);
                var entry = (RedisResult[])entries[0];
                var id = (string)entry[0];
                var fields = (RedisResult[])entry[1];
                string payload = null;
                for (int i = 0; i < fields.Length; i += 2)
                {
                    var fname = (string)fields[i];
                    var fval = (string)fields[i + 1];
                    if (fname == "payload") { payload = fval; break; }
                }
                return (id, payload);
            }
            catch { return (null, null); }
        }

        public async Task AckAsync(string queueName, string messageId, CancellationToken cancellationToken = default)
        {
            try
            {
                await Db.ExecuteAsync("XACK", queueName, _groupName, messageId).ConfigureAwait(false);
                await Db.ExecuteAsync("XDEL", queueName, messageId).ConfigureAwait(false);
            }
            catch { }
        }

        public async Task NackAsync(string queueName, string messageId, CancellationToken cancellationToken = default)
        {
            try
            {
                var res = await Db.ExecuteAsync("XRANGE", queueName, messageId, messageId).ConfigureAwait(false);
                if (!res.IsNull)
                {
                    var outer = (RedisResult[])res;
                    if (outer.Length > 0)
                    {
                        var entry = (RedisResult[])outer[0];
                        var fields = (RedisResult[])entry[1];
                        string payload = null;
                        for (int i = 0; i < fields.Length; i += 2)
                        {
                            var fname = (string)fields[i];
                            var fval = (string)fields[i + 1];
                            if (fname == "payload") { payload = fval; break; }
                        }
                        if (payload != null)
                        {
                            await Db.ExecuteAsync("XADD", $"dlq:{queueName}", "*", "payload", payload).ConfigureAwait(false);
                        }
                    }
                }
                await Db.ExecuteAsync("XACK", queueName, _groupName, messageId).ConfigureAwait(false);
                await Db.ExecuteAsync("XDEL", queueName, messageId).ConfigureAwait(false);
            }
            catch { }
        }

        // Reclaim pending entries older than reclaimMinIdleMs and return number reclaimed
        public async Task<int> ReclaimPendingAsync(string queueName, int count = 10, CancellationToken cancellationToken = default)
        {
            try
            {
                // Use XAUTOCLAIM if supported; fall back to XPENDING + XCLAIM for older Redis
                try
                {
                    var reclaimRes = await Db.ExecuteAsync("XAUTOCLAIM", queueName, _groupName, _consumerName, _reclaimMinIdleMs.ToString(), "0-0", "COUNT", count.ToString()).ConfigureAwait(false);
                    if (!reclaimRes.IsNull)
                    {
                        var reclaimOuter = (RedisResult[])reclaimRes;
                        if (reclaimOuter.Length >= 2)
                        {
                            var entries = (RedisResult[])reclaimOuter[1];
                            return entries.Length;
                        }
                    }
                }
                catch (RedisServerException ex) when (ex.Message != null && ex.Message.Contains("unknown command", StringComparison.OrdinalIgnoreCase))
                {
                    // fall back
                }

                // Fallback: XPENDING to list pending and XCLAIM each old entry
                var pendingRes = await Db.ExecuteAsync("XPENDING", queueName, _groupName, "-", "+", count.ToString()).ConfigureAwait(false);
                if (pendingRes.IsNull) return 0;

                var pendingOuter = (RedisResult[])pendingRes;
                int reclaimed = 0;
                foreach (var item in pendingOuter)
                {
                    var parts = (RedisResult[])item;
                    if (parts.Length >= 4)
                    {
                        var id = (string)parts[0];
                        // idle time is third element in milliseconds when using XPENDING with range
                        if (int.TryParse(parts[2].ToString(), out var idleMs))
                        {
                            if (idleMs >= _reclaimMinIdleMs)
                            {
                                try
                                {
                                    await Db.ExecuteAsync("XCLAIM", queueName, _groupName, _consumerName, _reclaimMinIdleMs.ToString(), id).ConfigureAwait(false);
                                    reclaimed++;
                                }
                                catch { }
                            }
                        }
                    }
                }

                return reclaimed;
            }
            catch { }

            return 0;
        }

        public async Task<long> GetLengthAsync(string queueName, CancellationToken cancellationToken = default)
        {
            var res = await Db.ExecuteAsync("XLEN", queueName).ConfigureAwait(false);
            long len = 0;
            if (!res.IsNull && long.TryParse(res.ToString(), out var v)) len = v;

            // update DLQ length metric
            try
            {
                var dlqRes = await Db.ExecuteAsync("XLEN", $"dlq:{queueName}").ConfigureAwait(false);
                long dlqLen = 0;
                if (!dlqRes.IsNull && long.TryParse(dlqRes.ToString(), out var dv)) dlqLen = dv;
                MetricsRegistry.AgentDlqLength.WithLabels(queueName).Set(dlqLen);
            }
            catch { }

            // update pending count metric (XPENDING <stream> <group>) -> first element is count
            try
            {
                var pendingRes = await Db.ExecuteAsync("XPENDING", queueName, _groupName).ConfigureAwait(false);
                long pending = 0;
                if (!pendingRes.IsNull)
                {
                    var s = pendingRes.ToString();
                    if (long.TryParse(s, out var pv)) pending = pv;
                }
                MetricsRegistry.AgentPendingCount.WithLabels(queueName).Set(pending);
            }
            catch { }

            return len;
        }
    }
}
