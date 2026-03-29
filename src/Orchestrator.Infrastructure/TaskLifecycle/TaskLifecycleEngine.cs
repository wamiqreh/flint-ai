using System;
using System.Text.Json;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Orchestrator.Core.TaskLifecycle;
using Orchestrator.Core.Queue;
using Orchestrator.Core.Agents;
using Orchestrator.Core;
using Orchestrator.Infrastructure.Metrics;
using Orchestrator.Infrastructure.Workflow;
using Polly;
using System.Diagnostics;
using System.Net.Http;
using System.Net.Http.Headers;

namespace Orchestrator.Infrastructure.TaskLifecycle
{
    public class TaskLifecycleEngine
    {
        private static readonly ActivitySource s_activity = new ActivitySource("Orchestrator.Core.TaskLifecycle");
        private static readonly HttpClient s_webhookHttpClient = new HttpClient();

        private readonly ITaskStore _store;
        readonly IQueueAdapter _queue;
        readonly AgentRegistry _registry;
        readonly AgentConcurrencyManager _concurrencyManager;
        readonly WorkflowEngine _workflowEngine;
        public TaskLifecycleEngine(ITaskStore store, IQueueAdapter queue, AgentRegistry registry, AgentConcurrencyManager concurrencyManager, Orchestrator.Infrastructure.Workflow.WorkflowEngine workflowEngine = null)
        {
            _store = store;
            _queue = queue;
            _registry = registry;
            _concurrencyManager = concurrencyManager;
            _workflowEngine = workflowEngine;
        }

        public async Task EnqueueTaskAsync(TaskRecord task, CancellationToken cancellationToken = default)
        {
            // persist as queued and push to queue
            await _store.CreateAsync(task with { State = TaskState.Queued }, cancellationToken);
            var payload = JsonSerializer.Serialize(new { task.Id });
            await _queue.EnqueueAsync("tasks", payload, cancellationToken);
            // update queue length metric if available
            try
            {
                var len = await _queue.GetLengthAsync("tasks", cancellationToken);
                MetricsRegistry.QueueLength.Set(len);
            }
            catch { }
        }

        public async Task ProcessNextAsync(CancellationToken cancellationToken = default)
        {
            var item = await _queue.DequeueAsync("tasks", cancellationToken);
            if (item.Payload == null) return;

            // parse id
            try
            {
                var doc = JsonDocument.Parse(item.Payload);
                var id = doc.RootElement.GetProperty("Id").GetString() ?? doc.RootElement.GetProperty("id").GetString();
                if (id == null)
                {
                    await _queue.NackAsync("tasks", item.MessageId, cancellationToken);
                    return;
                }

                using var activity = s_activity.StartActivity("ProcessTask", ActivityKind.Consumer);
                activity?.SetTag("task.id", id);

                // mark running
                await _store.UpdateStateAsync(id, TaskState.Running, cancellationToken);
                var record = await _store.GetAsync(id);
                if (record == null)
                {
                    await _queue.NackAsync("tasks", item.MessageId, cancellationToken);
                    return;
                }

                MetricsRegistry.TasksProcessed.Inc();
                object agentObj = null;
                try
                {
                    agentObj = _registry.Create(record.AgentType);
                }
                catch
                {
                    agentObj = null;
                }

                if (agentObj is IAgent agent)
                {
                    var def = new TaskDefinition(record.Id, record.AgentType, record.Prompt, record.WorkflowId);
                    var ctx = new AgentContext(record.Id, record.WorkflowId, "", "normal");
                    AgentResult result;
                    var sem = _concurrencyManager.GetSemaphore(record.AgentType);
                    var limit = _concurrencyManager.GetConcurrencyLimit(record.AgentType);
                    // update configured limit metric
                    try { Orchestrator.Infrastructure.Metrics.MetricsRegistry.AgentConcurrencyLimit.WithLabels(record.AgentType).Set(limit); } catch { }
                    await sem.WaitAsync(cancellationToken);
                    try
                    {
                        // update used metric after acquiring
                        try
                        {
                            var used = limit - sem.CurrentCount;
                            Orchestrator.Infrastructure.Metrics.MetricsRegistry.AgentConcurrencyUsed.WithLabels(record.AgentType).Set(used);
                        }
                        catch { }

                        // Retry policy for transient failures (e.g., rate limits). Exponential backoff + jitter, honors Retry-After when provided.
                        var rand = new Random();
                        var retryPolicy = Polly.Policy.Handle<Exception>()
                            .WaitAndRetryAsync(5, attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt)) + TimeSpan.FromMilliseconds(rand.Next(0, 500)),
                                (ex, timespan, retryCount, context) =>
                                {
                                    Console.WriteLine($"[TaskLifecycle] Retry {retryCount} for task {id} after {timespan} due to: {ex.Message}");
                                });
                        try
                        {
                            using (var a = s_activity.StartActivity("Agent.Execute", ActivityKind.Internal))
                            {
                                a?.SetTag("agent.type", record.AgentType);
                                a?.SetTag("workflow.id", record.WorkflowId ?? string.Empty);
                                result = await retryPolicy.ExecuteAsync(async () =>
                                {
                                    return await agent.ExecuteAsync(def, ctx, cancellationToken);
                                });
                            }
                        }
                        catch (Exception ex)
                        {
                            // Final failure after retries
                            result = new AgentResult(record.Id, false, null, ex.ToString());
                        }
                    }
                    finally
                    {
                        try
                        {
                            var usedAfter = limit - sem.CurrentCount + 1; // since Release will increment CurrentCount
                            // compute used after release more directly: usedBefore = limit - CurrentCount; after release used = usedBefore -1
                        }
                        catch { }
                        sem.Release();
                        try
                        {
                            var usedNow = limit - sem.CurrentCount;
                            Orchestrator.Infrastructure.Metrics.MetricsRegistry.AgentConcurrencyUsed.WithLabels(record.AgentType).Set(usedNow);
                        }
                        catch { }
                    }
                    await _store.SaveResultAsync(id, JsonSerializer.Serialize(result), cancellationToken);
                    var finalState = result.Success ? TaskState.Succeeded : TaskState.Failed;
                    await _store.UpdateStateAsync(id, finalState, cancellationToken);
                    if (result.Success) { MetricsRegistry.TasksSucceeded.Inc(); }
                    else { MetricsRegistry.TasksFailed.Inc(); }

                    // notify workflow engine
                    try
                    {
                        using var w = s_activity.StartActivity("Workflow.Notify", ActivityKind.Internal);
                        w?.SetTag("workflow.id", record.WorkflowId ?? string.Empty);

                        if (result.Success)
                        {
                            await _workflowEngine?.OnTaskCompletedAsync(id, record.WorkflowId, cancellationToken);
                        }
                        else
                        {
                            await _workflowEngine?.OnTaskFailedAsync(id, record.WorkflowId, cancellationToken);
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"[WorkflowEngine] notification failed: {ex.Message}");
                    }

                    await SendCompletionWebhookAsync(record, result, finalState, cancellationToken);
                    await _queue.AckAsync("tasks", item.MessageId, cancellationToken);
                }
                else
                {
                    await _store.SaveResultAsync(id, JsonSerializer.Serialize(new { error = "agent_not_found" }), cancellationToken);
                    await _store.UpdateStateAsync(id, TaskState.Failed, cancellationToken);
                    MetricsRegistry.TasksFailed.Inc();
                    var failedResult = new AgentResult(id, false, null, "agent_not_found");
                    await SendCompletionWebhookAsync(record, failedResult, TaskState.Failed, cancellationToken);
                    await _queue.AckAsync("tasks", item.MessageId, cancellationToken);
                }
            }
            catch (JsonException)
            {
                await _queue.NackAsync("tasks", item.MessageId, cancellationToken);
            }
        }

        private static async Task SendCompletionWebhookAsync(TaskRecord record, AgentResult result, TaskState state, CancellationToken cancellationToken)
        {
            var webhookUrl = Environment.GetEnvironmentVariable("TASK_COMPLETION_WEBHOOK_URL");
            if (string.IsNullOrWhiteSpace(webhookUrl))
            {
                return;
            }

            var request = new HttpRequestMessage(HttpMethod.Post, webhookUrl);
            var bearer = Environment.GetEnvironmentVariable("TASK_COMPLETION_WEBHOOK_BEARER_TOKEN");
            if (!string.IsNullOrWhiteSpace(bearer))
            {
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
            }

            var payload = JsonSerializer.Serialize(new
            {
                taskId = record.Id,
                agentType = record.AgentType,
                workflowId = record.WorkflowId,
                state = state.ToString(),
                success = result.Success,
                output = result.Output,
                error = result.Error
            });
            request.Content = new StringContent(payload, Encoding.UTF8, "application/json");

            try
            {
                using var response = await s_webhookHttpClient.SendAsync(request, cancellationToken);
                if (!response.IsSuccessStatusCode)
                {
                    Console.WriteLine($"[Webhook] non-success HTTP {(int)response.StatusCode} for task {record.Id}");
                }
            }
            catch (HttpRequestException ex)
            {
                Console.WriteLine($"[Webhook] request error for task {record.Id}: {ex.Message}");
            }
            catch (TaskCanceledException ex)
            {
                Console.WriteLine($"[Webhook] timeout/cancellation for task {record.Id}: {ex.Message}");
            }
        }
    }
}


