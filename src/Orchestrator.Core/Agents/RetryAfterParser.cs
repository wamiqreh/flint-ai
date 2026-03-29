using System;
using System.Net.Http;
using System.Linq;


namespace Orchestrator.Core.Agents
{
    public static class RetryAfterParser
    {
        public static TimeSpan Parse(HttpResponseMessage resp)
        {
            if (resp == null) return TimeSpan.FromSeconds(30);
            if (resp.Headers.TryGetValues("Retry-After", out var vals))
            {
                var v = vals.FirstOrDefault();
                if (int.TryParse(v, out var seconds)) return TimeSpan.FromSeconds(seconds);
                if (DateTimeOffset.TryParse(v, out var dt))
                {
                    var diff = dt - DateTimeOffset.UtcNow;
                    return diff > TimeSpan.Zero ? diff : TimeSpan.FromSeconds(30);
                }
            }
            return TimeSpan.FromSeconds(30);
        }
    }
}
