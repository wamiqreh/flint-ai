using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Core.Agents
{
    public class OpenAiSdkAdapter
    {
        private readonly string _apiKey;
        private readonly string _apiUrl;
        private readonly string _model;
        private readonly HttpClient _http;

        public OpenAiSdkAdapter(string apiKey, string apiUrl = null, string model = null, HttpClient httpClient = null)
        {
            _apiKey = apiKey ?? throw new ArgumentNullException(nameof(apiKey));
            _apiUrl = apiUrl ?? Environment.GetEnvironmentVariable("OPENAI_API_URL") ?? "https://api.openai.com/v1/chat/completions";
            _model = model ?? Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";
            _http = httpClient ?? new HttpClient();
        }

        public async Task<string> SendPromptAsync(string prompt, CancellationToken cancellationToken = default)
        {
            var req = new HttpRequestMessage(HttpMethod.Post, _apiUrl);
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _apiKey);
            req.Content = new StringContent(
                JsonSerializer.Serialize(new
                {
                    model = _model,
                    messages = new[] { new { role = "user", content = prompt } }
                }),
                Encoding.UTF8,
                "application/json");

            var resp = await _http.SendAsync(req, cancellationToken);
            if (resp.StatusCode == System.Net.HttpStatusCode.TooManyRequests)
            {
                throw new AgentRetryAfterException("OpenAI rate limited", RetryAfterParser.Parse(resp));
            }

            var body = await resp.Content.ReadAsStringAsync(cancellationToken);
            if (!resp.IsSuccessStatusCode)
            {
                throw new InvalidOperationException($"OpenAI returned HTTP {(int)resp.StatusCode}: {body}");
            }

            return body;
        }

        public static string ExtractText(string raw)
        {
            using var doc = JsonDocument.Parse(raw);
            var root = doc.RootElement;
            if (!root.TryGetProperty("choices", out var choices) || choices.ValueKind != JsonValueKind.Array || choices.GetArrayLength() == 0)
            {
                return raw;
            }

            var first = choices[0];
            if (first.TryGetProperty("message", out var msg) &&
                msg.ValueKind == JsonValueKind.Object &&
                msg.TryGetProperty("content", out var content) &&
                content.ValueKind == JsonValueKind.String)
            {
                return content.GetString() ?? string.Empty;
            }

            return raw;
        }
    }
}
