using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Core.Agents
{
    // Placeholder Claude wrapper — will call Claude API/SDK in full implementation.
    public class ClaudeAgent : IAgent
    {
        private readonly string _apiKey;
        private readonly ClaudeSdkAdapter _adapter;

        public ClaudeAgent()
        {
            _apiKey = Environment.GetEnvironmentVariable("CLAUDE_API_KEY");
            if (string.IsNullOrEmpty(_apiKey))
            {
                Console.WriteLine("[ClaudeAgent] Warning: CLAUDE_API_KEY not set — running in stub mode.");
                _adapter = null;
            }
            else
            {
                var apiUrl = Environment.GetEnvironmentVariable("CLAUDE_API_URL");
                _adapter = new ClaudeSdkAdapter(_apiKey, apiUrl, new HttpClient());
            }
        }

        public string AgentType => "claude";

        public async Task<AgentResult> ExecuteAsync(TaskDefinition task, AgentContext context, CancellationToken cancellationToken)
        {
            if (_adapter == null)
            {
                var output = $"[Claude stub] (no API key) Responded to prompt: {task.Prompt}";
                return new AgentResult(task.Id, true, output);
            }

            try
            {
                var raw = await _adapter.SendPromptAsync(task.Prompt, cancellationToken);
                var parsed = ClaudeSdkAdapter.ExtractText(raw);
                return new AgentResult(task.Id, true, parsed);
            }
            catch (AgentRetryAfterException) { throw; }
            catch (Exception ex)
            {
                return new AgentResult(task.Id, false, null, ex.ToString());
            }
        }
    }
}
