using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Hosting;
using Orchestrator.Infrastructure.TaskLifecycle;
using Microsoft.Extensions.Logging;

namespace Orchestrator.Api.HostedServices
{
    public class TaskWorkerHostedService : BackgroundService
    {
        readonly TaskLifecycleEngine _engine;
        readonly ILogger<TaskWorkerHostedService> _log;
        public TaskWorkerHostedService(TaskLifecycleEngine engine, ILogger<TaskWorkerHostedService> log)
        {
            _engine = engine;
            _log = log;
        }

        protected override async Task ExecuteAsync(CancellationToken stoppingToken)
        {
            _log.LogInformation("TaskWorkerHostedService started");
            while (!stoppingToken.IsCancellationRequested)
            {
                try
                {
                    await _engine.ProcessNextAsync(stoppingToken);
                }
                catch (System.OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    // graceful
                }
                catch (System.Exception ex)
                {
                    _log.LogError(ex, "Error processing task");
                    await Task.Delay(1000, stoppingToken);
                }
            }
            _log.LogInformation("TaskWorkerHostedService stopping");
        }
    }
}
