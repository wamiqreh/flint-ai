using System;
using System.Net.Http;
using Xunit;
using Orchestrator.Core.Agents;

namespace Orchestrator.Core.Tests
{
    public class RetryAfterParserTests
    {
        [Fact]
        public void ParsesSecondsValue()
        {
            var resp = new HttpResponseMessage(System.Net.HttpStatusCode.TooManyRequests);
            resp.Headers.TryAddWithoutValidation("Retry-After", "120");
n            var ts = RetryAfterParser.Parse(resp);
            Assert.True(ts.TotalSeconds >= 119 && ts.TotalSeconds <= 121);
        }
n        [Fact]
        public void ParsesHttpDateValue()
        {
            var date = DateTimeOffset.UtcNow.AddSeconds(45).ToString("r");
            var resp = new HttpResponseMessage(System.Net.HttpStatusCode.TooManyRequests);
            resp.Headers.TryAddWithoutValidation("Retry-After", date);
n            var ts = RetryAfterParser.Parse(resp);
            Assert.True(ts.TotalSeconds > 40 && ts.TotalSeconds <= 50);
        }
n        [Fact]
        public void DefaultsOnMissingOrInvalid()
        {
            var resp = new HttpResponseMessage(System.Net.HttpStatusCode.TooManyRequests);
            var ts = RetryAfterParser.Parse(resp);
            Assert.True(ts.TotalSeconds >= 29 && ts.TotalSeconds <= 31);
        }
    }
}




