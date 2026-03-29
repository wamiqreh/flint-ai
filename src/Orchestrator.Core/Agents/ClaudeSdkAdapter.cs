using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Runtime.CompilerServices;

namespace Orchestrator.Core.Agents
{
    public class ClaudeSdkAdapter
    {
        private readonly string _apiKey;
        private readonly string _apiUrl;
        private readonly HttpClient _http;

        public ClaudeSdkAdapter(string apiKey, string apiUrl = null, HttpClient httpClient = null)
        {
            _apiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
            _apiUrl = apiUrl ?? Environment.GetEnvironmentVariable("CLAUDE_API_URL") ?? "https://api.claude.example/v1/generate";
            _http = httpClient ?? new HttpClient();
        }

        public async Task<string> SendPromptAsync(string prompt, CancellationToken cancellationToken = default)
        {
            var req = new HttpRequestMessage(HttpMethod.Post, _apiUrl);
            req.Headers.Add("x-api-key", _apiKey);
            req.Headers.Add("anthropic-version", Environment.GetEnvironmentVariable("CLAUDE_API_VERSION") ?? "2023-06-01");
            req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            var model = Environment.GetEnvironmentVariable("CLAUDE_MODEL") ?? "claude-3-5-haiku-latest";
            var payload = System.Text.Json.JsonSerializer.Serialize(new
            {
                model,
                max_tokens = 1024,
                messages = new[] { new { role = "user", content = prompt } }
            });
            req.Content = new StringContent(payload, System.Text.Encoding.UTF8, "application/json");

            HttpResponseMessage resp;
            try
            {
                resp = await _http.SendAsync(req, cancellationToken);
            }
            catch (Exception ex)
            {
                throw new Exception("Claude SDK adapter HTTP failure", ex);
            }

            if (resp.StatusCode == System.Net.HttpStatusCode.TooManyRequests)
            {
                var retryAfter = RetryAfterParser.Parse(resp);
                throw new AgentRetryAfterException("Claude rate limited", retryAfter);
            }

            if (!resp.IsSuccessStatusCode)
            {
                var body = await resp.Content.ReadAsStringAsync(cancellationToken);
                throw new Exception($"Claude returned HTTP {(int)resp.StatusCode}: {body}");
            }

            var text = await resp.Content.ReadAsStringAsync(cancellationToken);
            return text;
        }

        public static string ExtractText(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw)) return string.Empty;
            try
            {
                using var doc = System.Text.Json.JsonDocument.Parse(raw);
                var root = doc.RootElement;
                if (root.TryGetProperty("content", out var contentArr) &&
                    contentArr.ValueKind == System.Text.Json.JsonValueKind.Array &&
                    contentArr.GetArrayLength() > 0)
                {
                    foreach (var item in contentArr.EnumerateArray())
                    {
                        if (item.ValueKind == System.Text.Json.JsonValueKind.Object &&
                            item.TryGetProperty("type", out var t) &&
                            t.ValueKind == System.Text.Json.JsonValueKind.String &&
                            t.GetString() == "text" &&
                            item.TryGetProperty("text", out var txt) &&
                            txt.ValueKind == System.Text.Json.JsonValueKind.String)
                        {
                            return txt.GetString() ?? string.Empty;
                        }
                    }
                }
            }
            catch
            {
            }

            return raw;
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
                throw new Exception("Claude SDK adapter HTTP failure", ex);
            }

            if (resp.StatusCode == System.Net.HttpStatusCode.TooManyRequests)
            {
                var retryAfter = RetryAfterParser.Parse(resp);
                throw new AgentRetryAfterException("Claude rate limited", retryAfter);
            }

            if (!resp.IsSuccessStatusCode)
            {
                var body = await resp.Content.ReadAsStringAsync(cancellationToken);
                throw new Exception($"Claude returned HTTP {(int)resp.StatusCode}: {body}");
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
