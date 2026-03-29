using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.Agents;
using Xunit;

namespace Orchestrator.Core.Tests
{
    class FakeHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> _responder;
        public FakeHandler(Func<HttpRequestMessage, HttpResponseMessage> responder) => _responder = responder;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            return Task.FromResult(_responder(request));
        }
    }

    public class CopilotSdkAdapterTests
    {
        [Fact]
        public async Task SendPromptAsync_ThrowsAgentRetryAfter_On429Seconds()
        {
            var handler = new FakeHandler(_ =>
            {
                var r = new HttpResponseMessage((HttpStatusCode)429);
                r.Headers.Add("Retry-After", "5");
                r.Content = new StringContent("rate limited");
                return r;
            });

            var client = new HttpClient(handler);
            var adapter = new CopilotSdkAdapter("key", "https://api.test", client);

            await Assert.ThrowsAsync<AgentRetryAfterException>(async () => await adapter.SendPromptAsync("hi"));
        }

        [Fact]
        public async Task SendPromptAsync_ReturnsBody_On200()
        {
            var handler = new FakeHandler(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"out\":\"ok\"}") });
            var client = new HttpClient(handler);
            var adapter = new CopilotSdkAdapter("key", "https://api.test", client);
            var res = await adapter.SendPromptAsync("hello");
            Assert.Contains("ok", res);
        }
    }
}




