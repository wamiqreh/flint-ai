using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;
using Orchestrator.Core.Agents;
using Xunit;

namespace Orchestrator.Core.Tests
{
    public class ClaudeSdkAdapterStreamingTests
    {
        class FakeHandler : HttpMessageHandler
        {
            private readonly Func<HttpRequestMessage, HttpResponseMessage> _responder;
            public FakeHandler(Func<HttpRequestMessage, HttpResponseMessage> responder) => _responder = responder;
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, System.Threading.CancellationToken cancellationToken)
            {
                return Task.FromResult(_responder(request));
            }
        }

        [Fact]
        public async Task SendPromptStreamingAsync_YieldsContent()
        {
            var handler = new FakeHandler(_ => new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("streamed content") });
            var client = new HttpClient(handler);
            var adapter = new ClaudeSdkAdapter("key", "https://api.test", client);
            var enumerator = adapter.SendPromptStreamingAsync("hello").GetAsyncEnumerator();
            Assert.True(await enumerator.MoveNextAsync());
            Assert.Contains("streamed content", enumerator.Current);
        }
    }
}




