using System;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Core.Agents
{
    public class DummyAgent : IAgent
    {
        public string AgentType => "dummy";

        private readonly string _copilotKey;
        private readonly string _claudeKey;
        private readonly bool _enableStreaming;

        public DummyAgent()
        {
            _copilotKey = Environment.GetEnvironmentVariable("COPILOT_API_KEY") ?? string.Empty;
            _claudeKey = Environment.GetEnvironmentVariable("CLAUDE_API_KEY") ?? string.Empty;
            _enableStreaming = string.Equals(Environment.GetEnvironmentVariable("ENABLE_AGENT_STREAMING"), "true", StringComparison.OrdinalIgnoreCase);
        }

        public async Task<AgentResult> ExecuteAsync(TaskDefinition task, AgentContext context, CancellationToken cancellationToken)
        {
            // Simulate light work and optionally indicate streaming capability
            var rnd = new Random();
            var delay = rnd.Next(50, 300);
            await Task.Delay(delay, cancellationToken);

            var streamingNote = _enableStreaming ? "streaming:enabled" : "streaming:disabled";
            var credsNote = (!string.IsNullOrEmpty(_copilotKey) ? "copilot:configured" : "copilot:missing") + ";" +
                            (!string.IsNullOrEmpty(_claudeKey) ? "claude:configured" : "claude:missing");

            var output = $"[DummyAgent] processed task {task.Id}: {task.Prompt} ({streamingNote}; {credsNote})";
            Console.WriteLine(output);

            var result = new AgentResult(task.Id, true, output, null);
            return result;
        }
    }
}
