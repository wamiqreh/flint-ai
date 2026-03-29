using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Core.Agents
{
    /// <summary>
    /// Generic webhook agent — forwards tasks to any external HTTP endpoint.
    /// This is the primary integration point for external agent frameworks:
    ///   - OpenAI Agents SDK (Python)
    ///   - Claude with tool use
    ///   - LangChain / LangGraph agents
    ///   - CrewAI crews
    ///   - Any custom agent running as an HTTP service
    ///
    /// Configuration via environment variables:
    ///   WEBHOOK_AGENT_URL      — Base URL of the agent service (required)
    ///   WEBHOOK_AGENT_TOKEN    — Bearer token for auth (optional)
    ///   WEBHOOK_AGENT_TIMEOUT  — Timeout in seconds (default: 300)
    ///
    /// Or per workflow node, set agentType to "webhook" and include metadata
    /// in the prompt as JSON: {"url":"http://my-agent:8000/run","prompt":"Do X"}
    /// </summary>
    public class WebhookAgent : IAgent
    {
        private static readonly HttpClient s_http = new();
        private readonly string _baseUrl;
        private readonly string _bearerToken;
        private readonly int _timeoutSeconds;

        public WebhookAgent()
        {
            _baseUrl = Environment.GetEnvironmentVariable("WEBHOOK_AGENT_URL");
            _bearerToken = Environment.GetEnvironmentVariable("WEBHOOK_AGENT_TOKEN");
            var timeoutStr = Environment.GetEnvironmentVariable("WEBHOOK_AGENT_TIMEOUT");
            _timeoutSeconds = int.TryParse(timeoutStr, out var t) ? t : 300;
        }

        public string AgentType => "webhook";

        public async Task<AgentResult> ExecuteAsync(TaskDefinition task, AgentContext context, CancellationToken cancellationToken)
        {
            // Determine target URL — check per-agent override, then global, then inline JSON
            string targetUrl = Environment.GetEnvironmentVariable($"WEBHOOK_AGENT_URL_{task.AgentType?.ToUpperInvariant()}")
                             ?? _baseUrl;
            string prompt = task.Prompt;

            // Support inline URL override: {"url":"...","prompt":"..."}
            if (!string.IsNullOrEmpty(task.Prompt) && task.Prompt.TrimStart().StartsWith("{"))
            {
                try
                {
                    using var doc = JsonDocument.Parse(task.Prompt);
                    if (doc.RootElement.TryGetProperty("url", out var urlProp))
                        targetUrl = urlProp.GetString();
                    if (doc.RootElement.TryGetProperty("prompt", out var promptProp))
                        prompt = promptProp.GetString();
                }
                catch (JsonException) { /* Not JSON — use raw prompt */ }
            }

            if (string.IsNullOrEmpty(targetUrl))
            {
                return new AgentResult(task.Id, false, null,
                    "No webhook URL configured. Set WEBHOOK_AGENT_URL env var or include {\"url\":\"...\",\"prompt\":\"...\"} in the prompt.");
            }

            try
            {
                var payload = JsonSerializer.Serialize(new
                {
                    task_id = task.Id,
                    agent_type = task.AgentType,
                    prompt,
                    workflow_id = task.WorkflowId,
                    context = new
                    {
                        task_id = context.TaskId,
                        workflow_id = context.WorkflowId,
                        language = context.Language,
                        priority = context.Priority
                    }
                });

                using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                cts.CancelAfter(TimeSpan.FromSeconds(_timeoutSeconds));

                var request = new HttpRequestMessage(HttpMethod.Post, targetUrl)
                {
                    Content = new StringContent(payload, Encoding.UTF8, "application/json")
                };

                if (!string.IsNullOrEmpty(_bearerToken))
                    request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _bearerToken);

                using var response = await s_http.SendAsync(request, cts.Token);
                var body = await response.Content.ReadAsStringAsync(cts.Token);

                if (!response.IsSuccessStatusCode)
                {
                    // Check for Retry-After header (rate limiting)
                    if ((int)response.StatusCode == 429 && response.Headers.RetryAfter?.Delta != null)
                    {
                        throw new AgentRetryAfterException("Rate limited by webhook", response.Headers.RetryAfter.Delta.Value);
                    }
                    return new AgentResult(task.Id, false, null, $"Webhook returned {(int)response.StatusCode}: {body}");
                }

                // Try to parse structured response: {"output":"...", "success": true}
                var output = TryExtractOutput(body);
                return new AgentResult(task.Id, true, output ?? body);
            }
            catch (AgentRetryAfterException) { throw; }
            catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                return new AgentResult(task.Id, false, null, $"Webhook timed out after {_timeoutSeconds}s");
            }
            catch (Exception ex)
            {
                return new AgentResult(task.Id, false, null, $"Webhook error: {ex.Message}");
            }
        }

        private static string TryExtractOutput(string body)
        {
            if (string.IsNullOrWhiteSpace(body)) return null;
            try
            {
                using var doc = JsonDocument.Parse(body);
                var root = doc.RootElement;
                // Standard response: {"output": "..."}
                if (root.TryGetProperty("output", out var o) && o.ValueKind == JsonValueKind.String)
                    return o.GetString();
                // Alternative: {"result": "..."}
                if (root.TryGetProperty("result", out var r) && r.ValueKind == JsonValueKind.String)
                    return r.GetString();
                // OpenAI Agents SDK style: {"final_output": "..."}
                if (root.TryGetProperty("final_output", out var fo) && fo.ValueKind == JsonValueKind.String)
                    return fo.GetString();
            }
            catch { }
            return null;
        }
    }
}
