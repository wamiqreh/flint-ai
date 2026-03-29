using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace Orchestrator.Core.Agents
{
    public class OpenAiAgent : IAgent
    {
        private readonly OpenAiSdkAdapter _adapter;

        public OpenAiAgent()
        {
            var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY");
            if (string.IsNullOrWhiteSpace(apiKey))
            {
                throw new InvalidOperationException("OPENAI_API_KEY is required for OpenAiAgent.");
            }

            var apiUrl = Environment.GetEnvironmentVariable("OPENAI_API_URL");
            var model = Environment.GetEnvironmentVariable("OPENAI_MODEL");
            _adapter = new OpenAiSdkAdapter(apiKey, apiUrl, model, new HttpClient());
        }

        public string AgentType => "openai";

        public async Task<AgentResult> ExecuteAsync(TaskDefinition task, AgentContext context, CancellationToken cancellationToken)
        {
            try
            {
                var raw = await _adapter.SendPromptAsync(task.Prompt, cancellationToken);
                var text = OpenAiSdkAdapter.ExtractText(raw);
                return new AgentResult(task.Id, true, text);
            }
            catch (AgentRetryAfterException)
            {
                throw;
            }
            catch (Exception ex)
            {
                return new AgentResult(task.Id, false, null, ex.ToString());
            }
        }
    }
}
