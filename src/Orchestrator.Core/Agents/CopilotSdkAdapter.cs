using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Runtime.CompilerServices;

namespace Orchestrator.Core.Agents
{
    public class CopilotSdkAdapter
    {
        private readonly string _apiKey;
        private readonly string _apiUrl;
        private readonly HttpClient _http;

        public CopilotSdkAdapter(string apiKey, string apiUrl = null, HttpClient httpClient = null)
        {
            _apiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
            _apiUrl = apiUrl ?? Environment.GetEnvironmentVariable("COPILOT_API_URL") ?? "https://api.copilot.example/v1/generate";
            _http = httpClient ?? new HttpClient();
        }

        public async Task<string> SendPromptAsync(string prompt, CancellationToken cancellationToken = default)
        {
            var req = new HttpRequestMessage(HttpMethod.Post, _apiUrl);
            req.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _apiKey);
            var payload = System.Text.Json.JsonSerializer.Serialize(new { prompt });
            req.Content = new StringContent(payload, System.Text.Encoding.UTF8, "application/json");

            HttpResponseMessage resp;
            try
            {
                resp = await _http.SendAsync(req, cancellationToken);
            }
            catch (Exception ex)
            {
                throw new Exception("Copilot SDK adapter HTTP failure", ex);
            }

            if (resp.StatusCode == System.Net.HttpStatusCode.TooManyRequests)
            {
                var retryAfter = RetryAfterParser.Parse(resp);
                throw new AgentRetryAfterException("Copilot rate limited", retryAfter);
            }

            if (!resp.IsSuccessStatusCode)
            {
                var body = await resp.Content.ReadAsStringAsync(cancellationToken);
                throw new Exception($"Copilot returned HTTP {(int)resp.StatusCode}: {body}");
            }

            var text = await resp.Content.ReadAsStringAsync(cancellationToken);
            return text;
        }

        public async IAsyncEnumerable<string> SendPromptStreamingAsync(string prompt, [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            var req = new HttpRequestMessage(HttpMethod.Post, _apiUrl);
            req.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _apiKey);
            var payload = System.Text.Json.JsonSerializer.Serialize(new { prompt, stream = true });
            req.Content = new StringContent(payload, System.Text.Encoding.UTF8, "application/json");

            HttpResponseMessage resp;
            try
            {
                resp = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            }
            catch (Exception ex)
            {
                throw new Exception("Copilot SDK adapter HTTP failure", ex);
            }

            if (resp.StatusCode == System.Net.HttpStatusCode.TooManyRequests)
            {
                var retryAfter = RetryAfterParser.Parse(resp);
                throw new AgentRetryAfterException("Copilot rate limited", retryAfter);
            }

            if (!resp.IsSuccessStatusCode)
            {
                var body = await resp.Content.ReadAsStringAsync(cancellationToken);
                throw new Exception($"Copilot returned HTTP {(int)resp.StatusCode}: {body}");
            }

            using var stream = await resp.Content.ReadAsStreamAsync(cancellationToken);
            using var reader = new System.IO.StreamReader(stream);
            char[] buffer = new char[1024];
            while (!reader.EndOfStream)
            {
                var read = await reader.ReadAsync(buffer, 0, buffer.Length);
                if (read > 0)
                {
                    yield return new string(buffer, 0, read);
                }
            }
        }
    }
}
