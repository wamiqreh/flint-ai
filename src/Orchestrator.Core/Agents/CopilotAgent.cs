using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Core.Agents
{
    // Copilot wrapper — uses CopilotSdkAdapter when COPILOT_API_KEY is present. Attempts to parse common JSON shapes.
    public class CopilotAgent : IAgent
    {
        private readonly string _apiKey;
        private readonly CopilotSdkAdapter _adapter;

        public CopilotAgent()
        {
            _apiKey = Environment.GetEnvironmentVariable("COPILOT_API_KEY");
            if (string.IsNullOrEmpty(_apiKey))
            {
                Console.WriteLine("[CopilotAgent] Warning: COPILOT_API_KEY not set — running in stub mode.");
                _adapter = null;
            }
            else
            {
                var apiUrl = Environment.GetEnvironmentVariable("COPILOT_API_URL");
                _adapter = new CopilotSdkAdapter(_apiKey, apiUrl, new HttpClient());
            }
        }

        public string AgentType => "copilot";

        public async Task<AgentResult> ExecuteAsync(TaskDefinition task, AgentContext context, CancellationToken cancellationToken)
        {
            if (_adapter == null)
            {
                var output = $"[Copilot stub] (no API key) Generated code for prompt: {task.Prompt}";
                return new AgentResult(task.Id, true, output);
            }

            try
            {
                var raw = await _adapter.SendPromptAsync(task.Prompt, cancellationToken);
                var parsed = TryExtractText(raw, out var text) ? text : raw;
                return new AgentResult(task.Id, true, parsed);
            }
            catch (AgentRetryAfterException) { throw; }
            catch (Exception ex)
            {
                return new AgentResult(task.Id, false, null, ex.ToString());
            }
        }

        private static bool TryExtractText(string raw, out string text)
        {
            text = null;
            if (string.IsNullOrWhiteSpace(raw)) return false;
            raw = raw.Trim();
            if (!raw.StartsWith("{") && !raw.StartsWith("[")) return false;
            try
            {
                using var doc = System.Text.Json.JsonDocument.Parse(raw);
                var root = doc.RootElement;
                if (root.ValueKind == System.Text.Json.JsonValueKind.Object)
                {
                    if (root.TryGetProperty("output", out var outp) && outp.ValueKind == System.Text.Json.JsonValueKind.String)
                    {
                        text = outp.GetString();
                        return true;
                    }
                    if (root.TryGetProperty("text", out var t) && t.ValueKind == System.Text.Json.JsonValueKind.String)
                    {
                        text = t.GetString();
                        return true;
                    }
                    if (root.TryGetProperty("result", out var r) && r.ValueKind == System.Text.Json.JsonValueKind.String)
                    {
                        text = r.GetString();
                        return true;
                    }
                    if (root.TryGetProperty("choices", out var choices) && choices.ValueKind == System.Text.Json.JsonValueKind.Array && choices.GetArrayLength() > 0)
                    {
                        var first = choices[0];
                        if (first.TryGetProperty("text", out var ft) && ft.ValueKind == System.Text.Json.JsonValueKind.String)
                        {
                            text = ft.GetString();
                            return true;
                        }
                    }
                }
                else if (root.ValueKind == System.Text.Json.JsonValueKind.Array && root.GetArrayLength() > 0)
                {
                    var first = root[0];
                    if (first.ValueKind == System.Text.Json.JsonValueKind.Object)
                    {
                        if (first.TryGetProperty("text", out var ft) && ft.ValueKind == System.Text.Json.JsonValueKind.String)
                        {
                            text = ft.GetString();
                            return true;
                        }
                    }
                }
            }
            catch { }

            return false;
        }
    }
}
