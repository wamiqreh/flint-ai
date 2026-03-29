using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Xunit;
using Orchestrator.Core.Agents;

namespace Orchestrator.Integration.Tests
{
    class FakeHttpMessageHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, int, HttpResponseMessage> _responder;
        private int _count = 0;
        public FakeHttpMessageHandler(Func<HttpRequestMessage, int, HttpResponseMessage> responder)
        {
            _responder = responder;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var current = System.Threading.Interlocked.Increment(ref _count);
            var resp = _responder(request, current);
            return Task.FromResult(resp);
        }
    }

    public class TaskLifecycleRateLimitTests
    {
        [Fact]
        public async Task AdapterRetryAfterIsHonoredByPolicy()
        {
            // Arrange: adapter returns 429 on first call with Retry-After 2s, then 200
            var handler = new FakeHttpMessageHandler((req, count) =>
            {
                if (count == 1)
                {
                    var r = new HttpResponseMessage((HttpStatusCode)429);
                    r.Headers.TryAddWithoutValidation("Retry-After", "2");
                    return r;
                }
                return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("ok-result") };
            });

            var http = new HttpClient(handler);
            var adapter = new CopilotSdkAdapter("test-key", "https://api.test", http);

            // Act
            var sw = System.Diagnostics.Stopwatch.StartNew();
            var result = await adapter.SendPromptAsync("hello", CancellationToken.None);
            sw.Stop();

            // Assert: ensure it waited at least 2s due to Retry-After before succeeding
            Assert.Equal("ok-result", result);
            Assert.True(sw.Elapsed.TotalSeconds >= 2, $"Elapsed {sw.Elapsed.TotalSeconds} should be >= 2");
        }
    }
}




