using System;
using System.IO;
using System.Linq;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Text.Json;
using System.Text;
using System.Net.WebSockets;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Serilog;
using Orchestrator.Core.TaskLifecycle;
using Orchestrator.Infrastructure.TaskStore;
using Orchestrator.Core.Queue;
using Orchestrator.Infrastructure.Queue;
using Orchestrator.Infrastructure.TaskLifecycle;
using Orchestrator.Core.Workflow;
using Orchestrator.Infrastructure.Workflow.WorkflowStore;
using Orchestrator.Infrastructure.Workflow;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Prometheus;
using Orchestrator.Api.HostedServices;

namespace Orchestrator.Api
{
    public class Program
    {
        public static async Task Main(string[] args)
        {
            var builder = WebApplication.CreateBuilder(args);

            // configure logging
            Log.Logger = new LoggerConfiguration().Enrich.FromLogContext().WriteTo.Console().CreateLogger();
            builder.Host.UseSerilog();
            builder.Services.AddEndpointsApiExplorer();
            builder.Services.AddSwaggerGen();
            builder.Services.AddHealthChecks()
                .AddCheck("self", () => HealthCheckResult.Healthy("ok"));
            builder.Services.AddCors(options =>
            {
                options.AddPolicy("default", policy =>
                {
                    policy.AllowAnyOrigin().AllowAnyHeader().AllowAnyMethod();
                });
            });

            // OpenTelemetry tracing (optional) - enable when OTEL_EXPORTER_OTLP_ENDPOINT is configured.
            try
            {
                builder.Services.AddOpenTelemetry()
                    .WithTracing(tracerProviderBuilder =>
                    {
                        tracerProviderBuilder
                            .SetResourceBuilder(ResourceBuilder.CreateDefault().AddService("Orchestrator"))
                            .AddAspNetCoreInstrumentation()
                            .AddHttpClientInstrumentation()
                            .AddSource("Orchestrator")
                            .AddOtlpExporter(opt =>
                            {
                                var endpoint = builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"] ?? Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT");
                                if (!string.IsNullOrEmpty(endpoint))
                                {
                                    opt.Endpoint = new Uri(endpoint);
                                }
                            });
                        // If no OTLP endpoint is configured, also add a Console exporter for local verification
                        tracerProviderBuilder.AddConsoleExporter();
                    });
            }
            catch
            {
                // If OpenTelemetry packages are not present or misconfigured, continue without tracing.
            }

            // configuration: choose stores and queue based on environment
            var conn = builder.Configuration.GetConnectionString("DefaultConnection");
            if (!string.IsNullOrEmpty(conn))
            {
                builder.Services.AddSingleton<ITaskStore>(_ => new PostgresTaskStore(conn));
                builder.Services.AddSingleton<IWorkflowStore>(_ => new PostgresWorkflowStore(conn));
            }
            else
            {
                builder.Services.AddSingleton<ITaskStore, InMemoryTaskStore>();
                builder.Services.AddSingleton<IWorkflowStore, Orchestrator.Infrastructure.Workflow.WorkflowStore.InMemoryWorkflowStore>();
            }

            var useInMemoryQueue = string.Equals(Environment.GetEnvironmentVariable("USE_INMEMORY_QUEUE"), "true", StringComparison.OrdinalIgnoreCase);
            if (useInMemoryQueue)
            {
                builder.Services.AddSingleton<IQueueAdapter, InMemoryQueueAdapter>();
            }
            else
            {
                builder.Services.AddSingleton<IQueueAdapter, Orchestrator.Infrastructure.Queue.RedisQueueAdapter>();
            }

            // Agent registry and sample agent
            builder.Services.AddSingleton<Orchestrator.Core.Agents.AgentRegistry>(sp =>
            {
                var registry = new Orchestrator.Core.Agents.AgentRegistry();
                registry.Register("dummy", () => new Orchestrator.Core.Agents.DummyAgent());
                registry.Register("copilot", () => new Orchestrator.Core.Agents.CopilotAgent());
                registry.Register("claude", () => new Orchestrator.Core.Agents.ClaudeAgent());
                registry.Register("openai", () => new Orchestrator.Core.Agents.OpenAiAgent());
                registry.Register("webhook", () => new Orchestrator.Core.Agents.WebhookAgent());
                return registry;
            });

            builder.Services.AddSingleton<AgentConcurrencyManager>();

            // register workflow engine
            builder.Services.AddSingleton<WorkflowEngine>(sp =>
            {
                return new WorkflowEngine(
                    sp.GetRequiredService<IWorkflowStore>(),
                    sp.GetRequiredService<IQueueAdapter>(),
                    sp.GetRequiredService<ITaskStore>());
            });

            // TaskLifecycleEngine after workflow engine so DI can provide it
            builder.Services.AddSingleton<TaskLifecycleEngine>(sp =>
            {
                return new TaskLifecycleEngine(
                    sp.GetRequiredService<ITaskStore>(),
                    sp.GetRequiredService<IQueueAdapter>(),
                    sp.GetRequiredService<Orchestrator.Core.Agents.AgentRegistry>(),
                    sp.GetRequiredService<AgentConcurrencyManager>(),
                    sp.GetRequiredService<WorkflowEngine>());
            });

            // Background worker to process queued tasks
            builder.Services.AddHostedService<TaskWorkerHostedService>();

            var app = builder.Build();

            app.UseSwagger();
            app.UseSwaggerUI();

            // enable request logging and routing
            app.UseSerilogRequestLogging();
            app.UseRouting();
            app.UseCors("default");
            app.UseWebSockets();
            app.Use(async (context, next) =>
            {
                var configuredApiKey = Environment.GetEnvironmentVariable("ORCHESTRATOR_API_KEY");
                if (string.IsNullOrWhiteSpace(configuredApiKey))
                {
                    await next();
                    return;
                }

                var path = context.Request.Path.Value ?? string.Empty;
                var allowAnonymous =
                    path.StartsWith("/health", StringComparison.OrdinalIgnoreCase) ||
                    path.StartsWith("/ready", StringComparison.OrdinalIgnoreCase) ||
                    path.StartsWith("/live", StringComparison.OrdinalIgnoreCase) ||
                    path.StartsWith("/swagger", StringComparison.OrdinalIgnoreCase) ||
                    path.StartsWith("/metrics", StringComparison.OrdinalIgnoreCase);

                if (allowAnonymous)
                {
                    await next();
                    return;
                }

                if (!context.Request.Headers.TryGetValue("X-API-Key", out var key) || key != configuredApiKey)
                {
                    context.Response.StatusCode = StatusCodes.Status401Unauthorized;
                    await context.Response.WriteAsJsonAsync(new { error = "unauthorized", message = "Missing or invalid X-API-Key" });
                    return;
                }

                await next();
            });
            // Serve static dashboard UI from wwwroot/dashboard (simple single-page app)
            app.UseStaticFiles();

            // database migrations
            if (!string.IsNullOrEmpty(conn))
            {
                var migrationsFolder = Path.Combine(AppContext.BaseDirectory, "Migrations");
                await MigrationRunner.RunMigrationsAsync(conn, migrationsFolder);
            }

            // Custom lightweight metrics endpoint (avoid System.Metrics adapter issues in some environments)
            app.MapGet("/metrics", async (Orchestrator.Core.Queue.IQueueAdapter queue, Orchestrator.Infrastructure.TaskLifecycle.AgentConcurrencyManager concurrencyManager, Orchestrator.Core.Agents.AgentRegistry registry) =>
            {
                // Build simple Prometheus exposition format for a few key metrics
                var lines = new System.Text.StringBuilder();
                lines.AppendLine("# HELP orchestrator_queue_length Queue length for default queue");
                lines.AppendLine("# TYPE orchestrator_queue_length gauge");
                try
                {
                    var len = await queue.GetLengthAsync("default");
                    lines.AppendLine($"orchestrator_queue_length {len}");
                }
                catch
                {
                    lines.AppendLine("orchestrator_queue_length 0");
                }

                lines.AppendLine("# HELP orchestrator_agent_concurrency_limit Configured concurrency limit per agent");
                lines.AppendLine("# TYPE orchestrator_agent_concurrency_limit gauge");
                try
                {
                    // Attempt to enumerate registered agents if available
                    var agentNames = new System.Collections.Generic.List<string>();
                    try
                    {
                        agentNames.AddRange(registry.GetRegisteredAgents());
                    }
                    catch
                    {
                        agentNames.Add("default");
                    }

                    foreach (var a in agentNames)
                    {
                        var lim = concurrencyManager.GetConcurrencyLimit(a);
                        lines.AppendLine($"orchestrator_agent_concurrency_limit{{agent=\"{a}\"}} {lim}");
                    }
                }
                catch { }

                return Results.Text(lines.ToString(), "text/plain; version=0.0.4");
            });

            // Dashboard endpoints
            app.MapGet("/dashboard/agents/concurrency", (Orchestrator.Infrastructure.TaskLifecycle.AgentConcurrencyManager concurrencyManager, Orchestrator.Core.Agents.AgentRegistry registry) =>
            {
                var agents = new System.Collections.Generic.List<object>();
                foreach (var name in registry.GetRegisteredAgents())
                {
                    agents.Add(new { agent = name, limit = concurrencyManager.GetConcurrencyLimit(name), used = concurrencyManager.GetCurrentUsage(name) });
                }
                return Results.Json(agents);
            });

            app.MapGet("/dashboard/workflows", async (Orchestrator.Core.Workflow.IWorkflowStore store) =>
            {
                var list = await store.ListAsync();
                return Results.Json(list);
            });

            app.MapGet("/dashboard/workflows/{id}/nodes", async (string id, Orchestrator.Core.Workflow.IWorkflowStore store) =>
            {
                var wf = await store.GetAsync(id);
                if (wf == null) return Results.NotFound();
                return Results.Json(wf.Nodes);
            });

            // Dead-letter queue endpoint (consumed by dashboard)
            app.MapGet("/dashboard/dlq", async (Orchestrator.Core.TaskLifecycle.ITaskStore store) =>
            {
                var tasks = await store.ListAsync();
                return Results.Json(tasks.Where(t => t.State == TaskState.DeadLetter)
                    .OrderByDescending(t => t.CreatedAt)
                    .Select(t => new { id = t.Id, agentType = t.AgentType, error = t.ResultJson, failedAt = t.CreatedAt }));
            });

            app.MapHealthChecks("/health");
            app.MapGet("/ready", () => Results.Ok(new { status = "ready" }));
            app.MapGet("/live", () => Results.Ok(new { status = "live" }));

            // Add HTTP task submission endpoint (case-insensitive keys)
            async Task<IResult> SubmitTask(HttpContext http, TaskLifecycleEngine engine)
            {
                try
                {
                    using var sr = new StreamReader(http.Request.Body);
                    var txt = await sr.ReadToEndAsync();
                    if (string.IsNullOrWhiteSpace(txt)) return Results.BadRequest(new { error = "empty_body" });
                    using var doc = JsonDocument.Parse(txt);
                    var root = doc.RootElement;
                    string agent = null, prompt = null, workflowId = null;
                    foreach (var prop in root.EnumerateObject())
                    {
                        if (string.Equals(prop.Name, "AgentType", StringComparison.OrdinalIgnoreCase)) agent = prop.Value.GetString();
                        if (string.Equals(prop.Name, "Prompt", StringComparison.OrdinalIgnoreCase)) prompt = prop.Value.GetString();
                        if (string.Equals(prop.Name, "WorkflowId", StringComparison.OrdinalIgnoreCase)) workflowId = prop.Value.GetString();
                    }

                    if (string.IsNullOrEmpty(agent) || string.IsNullOrEmpty(prompt)) return Results.BadRequest(new { error = "missing_agent_or_prompt" });
                    var id = Guid.NewGuid().ToString();
                    var rec = new TaskRecord(id, agent, prompt, workflowId, TaskState.Queued, null, DateTimeOffset.UtcNow);
                    await engine.EnqueueTaskAsync(rec);
                    return Results.Accepted($"/tasks/{id}", new { id });
                }
                catch (Exception ex)
                {
                    return Results.BadRequest(new { error = ex.Message });
                }
            }

            async Task<IResult> CreateWorkflow(JsonElement body, Orchestrator.Core.Workflow.IWorkflowStore store)
            {
                try
                {
                    var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
                    var def = JsonSerializer.Deserialize<WorkflowDefinition>(body.GetRawText(), options);
                    if (def == null || string.IsNullOrEmpty(def.Id)) return Results.BadRequest(new { error = "invalid_workflow" });
                    await store.CreateAsync(def);
                    return Results.Created($"/workflows/{def.Id}", def);
                }
                catch (Exception ex)
                {
                    return Results.BadRequest(new { error = ex.Message });
                }
            }

            async Task<IResult> StartWorkflow(string id, Orchestrator.Core.Workflow.IWorkflowStore store, TaskLifecycleEngine engine)
            {
                var def = await store.GetAsync(id);
                if (def == null) return Results.NotFound();

                var incoming = def.Edges.Select(e => e.ToNodeId).ToHashSet();
                var entryNodes = def.Nodes.Where(n => !incoming.Contains(n.Id)).ToList();
                foreach (var node in entryNodes)
                {
                    var newId = Guid.NewGuid().ToString();
                    if (node.HumanApproval)
                    {
                        // Human-in-the-loop entry node: create as Pending, don't enqueue
                        var pendingRec = new TaskRecord(newId, node.AgentType, node.PromptTemplate, def.Id, TaskState.Pending, null, DateTimeOffset.UtcNow);
                        await store.SetNodeTaskMappingAsync(def.Id, node.Id, newId);
                        await engine.CreatePendingTaskAsync(pendingRec);
                    }
                    else
                    {
                        var rec = new TaskRecord(newId, node.AgentType, node.PromptTemplate, def.Id, TaskState.Queued, null, DateTimeOffset.UtcNow);
                        await engine.EnqueueTaskAsync(rec);
                        await store.SetNodeTaskMappingAsync(def.Id, node.Id, newId);
                    }
                }
                return Results.Accepted($"/workflows/{id}/start");
            }

            async Task<IResult> GetTaskById(string id, Orchestrator.Core.TaskLifecycle.ITaskStore store)
            {
                var rec = await store.GetAsync(id);
                if (rec == null) return Results.NotFound();
                return Results.Json(new { id = rec.Id, state = rec.State.ToString(), result = rec.ResultJson, workflowId = rec.WorkflowId });
            }

            async Task StreamTaskSse(string id, HttpContext http, Orchestrator.Core.TaskLifecycle.ITaskStore store)
            {
                var initial = await store.GetAsync(id);
                if (initial == null)
                {
                    http.Response.StatusCode = 404;
                    return;
                }

                http.Response.Headers["Content-Type"] = "text/event-stream";
                http.Response.Headers["Cache-Control"] = "no-cache";
                http.Response.Headers["Connection"] = "keep-alive";

                var timeout = TimeSpan.FromSeconds(300);
                var sw = Stopwatch.StartNew();
                string lastStatus = null;

                while (!http.RequestAborted.IsCancellationRequested)
                {
                    if (sw.Elapsed >= timeout)
                    {
                        var tp = JsonSerializer.Serialize(new { taskId = id, timestamp = DateTimeOffset.UtcNow.ToString("o") });
                        await http.Response.WriteAsync($"event: timeout\ndata: {tp}\n\n", http.RequestAborted);
                        await http.Response.Body.FlushAsync(http.RequestAborted);
                        break;
                    }

                    TaskRecord rec;
                    try
                    {
                        rec = await store.GetAsync(id, http.RequestAborted);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }

                    if (rec == null) break;

                    var currentStatus = rec.State.ToString();
                    if (!string.Equals(currentStatus, lastStatus, StringComparison.Ordinal))
                    {
                        var sp = JsonSerializer.Serialize(new { taskId = rec.Id, status = currentStatus, timestamp = DateTimeOffset.UtcNow.ToString("o") });
                        await http.Response.WriteAsync($"event: status\ndata: {sp}\n\n", http.RequestAborted);
                        await http.Response.Body.FlushAsync(http.RequestAborted);
                        lastStatus = currentStatus;
                    }

                    if (rec.State == TaskState.Succeeded || rec.State == TaskState.Failed || rec.State == TaskState.DeadLetter)
                    {
                        var cp = JsonSerializer.Serialize(new
                        {
                            taskId = rec.Id,
                            status = currentStatus,
                            output = rec.State == TaskState.Succeeded ? rec.ResultJson : (string)null,
                            error = rec.State != TaskState.Succeeded ? rec.ResultJson : (string)null,
                            timestamp = DateTimeOffset.UtcNow.ToString("o")
                        });
                        await http.Response.WriteAsync($"event: complete\ndata: {cp}\n\n", http.RequestAborted);
                        await http.Response.Body.FlushAsync(http.RequestAborted);
                        break;
                    }

                    try
                    {
                        await Task.Delay(1000, http.RequestAborted);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                }
            }

            async Task StreamTaskWebSocket(string id, HttpContext http, Orchestrator.Core.TaskLifecycle.ITaskStore store)
            {
                if (!http.WebSockets.IsWebSocketRequest)
                {
                    http.Response.StatusCode = StatusCodes.Status400BadRequest;
                    return;
                }

                using var webSocket = await http.WebSockets.AcceptWebSocketAsync();
                string lastPayload = null;
                while (webSocket.State == WebSocketState.Open && !http.RequestAborted.IsCancellationRequested)
                {
                    var rec = await store.GetAsync(id, http.RequestAborted);
                    var payload = rec == null
                        ? JsonSerializer.Serialize(new { id, state = "NotFound", result = (string)null, workflowId = (string)null })
                        : JsonSerializer.Serialize(new { id = rec.Id, state = rec.State.ToString(), result = rec.ResultJson, workflowId = rec.WorkflowId });

                    if (!string.Equals(payload, lastPayload, StringComparison.Ordinal))
                    {
                        var bytes = Encoding.UTF8.GetBytes(payload);
                        await webSocket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, http.RequestAborted);
                        lastPayload = payload;
                    }

                    if (rec == null || rec.State == TaskState.Succeeded || rec.State == TaskState.Failed || rec.State == TaskState.DeadLetter)
                    {
                        await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, "complete", http.RequestAborted);
                        break;
                    }

                    await Task.Delay(1000, http.RequestAborted);
                }
            }

            async Task StreamWorkflowSse(string id, HttpContext http, Orchestrator.Core.Workflow.IWorkflowStore wfStore, Orchestrator.Core.TaskLifecycle.ITaskStore taskStore)
            {
                var wf = await wfStore.GetAsync(id);
                if (wf == null)
                {
                    http.Response.StatusCode = 404;
                    return;
                }

                http.Response.Headers["Content-Type"] = "text/event-stream";
                http.Response.Headers["Cache-Control"] = "no-cache";
                http.Response.Headers["Connection"] = "keep-alive";

                var timeout = TimeSpan.FromSeconds(300);
                var sw = Stopwatch.StartNew();
                var lastStatuses = new System.Collections.Generic.Dictionary<string, string>();

                while (!http.RequestAborted.IsCancellationRequested)
                {
                    if (sw.Elapsed >= timeout)
                    {
                        var tp = JsonSerializer.Serialize(new { workflowId = id, timestamp = DateTimeOffset.UtcNow.ToString("o") });
                        await http.Response.WriteAsync($"event: timeout\ndata: {tp}\n\n", http.RequestAborted);
                        await http.Response.Body.FlushAsync(http.RequestAborted);
                        break;
                    }

                    System.Collections.Generic.IEnumerable<TaskRecord> allTasks;
                    try
                    {
                        allTasks = await taskStore.ListAsync(http.RequestAborted);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }

                    var wfTasks = allTasks.Where(t => t.WorkflowId == id).ToList();

                    foreach (var task in wfTasks)
                    {
                        var currentStatus = task.State.ToString();
                        string nodeId = null;
                        try { nodeId = await wfStore.GetNodeIdForTaskAsync(id, task.Id); } catch { }

                        if (!lastStatuses.TryGetValue(task.Id, out var prev) || prev != currentStatus)
                        {
                            var ep = JsonSerializer.Serialize(new
                            {
                                workflowId = id,
                                taskId = task.Id,
                                nodeId = nodeId ?? "",
                                status = currentStatus,
                                timestamp = DateTimeOffset.UtcNow.ToString("o")
                            });
                            await http.Response.WriteAsync($"event: task-update\ndata: {ep}\n\n", http.RequestAborted);
                            await http.Response.Body.FlushAsync(http.RequestAborted);
                            lastStatuses[task.Id] = currentStatus;
                        }
                    }

                    if (wfTasks.Count > 0 && wfTasks.All(t =>
                        t.State == TaskState.Succeeded || t.State == TaskState.Failed || t.State == TaskState.DeadLetter))
                    {
                        var allSucceeded = wfTasks.All(t => t.State == TaskState.Succeeded);
                        var wp = JsonSerializer.Serialize(new
                        {
                            workflowId = id,
                            status = allSucceeded ? "Succeeded" : "Failed",
                            taskCount = wfTasks.Count,
                            timestamp = DateTimeOffset.UtcNow.ToString("o")
                        });
                        await http.Response.WriteAsync($"event: workflow-complete\ndata: {wp}\n\n", http.RequestAborted);
                        await http.Response.Body.FlushAsync(http.RequestAborted);
                        break;
                    }

                    try
                    {
                        await Task.Delay(1000, http.RequestAborted);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                }
            }

            // Task list with optional filters: ?state=Running&workflowId=test-flow
            async Task<IResult> ListTasks(HttpContext http, Orchestrator.Core.TaskLifecycle.ITaskStore store)
            {
                var tasks = await store.ListAsync();
                var result = tasks.AsEnumerable();
                var stateFilter = http.Request.Query["state"].FirstOrDefault();
                var workflowFilter = http.Request.Query["workflowId"].FirstOrDefault();
                if (!string.IsNullOrEmpty(stateFilter) && Enum.TryParse<TaskState>(stateFilter, true, out var state))
                    result = result.Where(t => t.State == state);
                if (!string.IsNullOrEmpty(workflowFilter))
                    result = result.Where(t => t.WorkflowId == workflowFilter);
                return Results.Json(result.OrderByDescending(t => t.CreatedAt).Select(t => new
                {
                    id = t.Id, agentType = t.AgentType, prompt = t.Prompt,
                    state = t.State.ToString(), workflowId = t.WorkflowId,
                    result = t.ResultJson, createdAt = t.CreatedAt
                }));
            }

            // Cancel a queued or running task
            async Task<IResult> CancelTask(string id, Orchestrator.Core.TaskLifecycle.ITaskStore store)
            {
                var rec = await store.GetAsync(id);
                if (rec == null) return Results.NotFound();
                if (rec.State == TaskState.Succeeded || rec.State == TaskState.Failed || rec.State == TaskState.DeadLetter)
                    return Results.BadRequest(new { error = "task_already_terminal" });
                await store.UpdateStateAsync(id, TaskState.Failed);
                await store.SaveResultAsync(id, JsonSerializer.Serialize(new { cancelled = true, error = "cancelled_by_user" }));
                return Results.Ok(new { id, state = "Failed", cancelled = true });
            }

            // Approve a human-in-the-loop node (Pending → Queued)
            async Task<IResult> ApproveNode(string id, string nodeId, WorkflowEngine workflowEngine)
            {
                await workflowEngine.ApproveNodeAsync(id, nodeId);
                return Results.Ok(new { workflowId = id, nodeId, action = "approved" });
            }

            // Reject a human-in-the-loop node (Pending → DeadLetter)
            async Task<IResult> RejectNode(string id, string nodeId, WorkflowEngine workflowEngine)
            {
                await workflowEngine.RejectNodeAsync(id, nodeId);
                return Results.Ok(new { workflowId = id, nodeId, action = "rejected" });
            }

            // Restart a dead-lettered or failed task (re-enqueue the same node)
            async Task<IResult> RestartTask(string id, Orchestrator.Core.TaskLifecycle.ITaskStore store,
                Orchestrator.Core.Workflow.IWorkflowStore wfStore, TaskLifecycleEngine engine)
            {
                var rec = await store.GetAsync(id);
                if (rec == null) return Results.NotFound();
                if (rec.State != TaskState.Failed && rec.State != TaskState.DeadLetter)
                    return Results.BadRequest(new { error = "task_not_failed_or_dlq" });

                // Create a new task with same parameters and enqueue it
                var newId = Guid.NewGuid().ToString();
                var newRec = new TaskRecord(newId, rec.AgentType, rec.Prompt, rec.WorkflowId, TaskState.Queued, null, DateTimeOffset.UtcNow);
                await engine.EnqueueTaskAsync(newRec);

                // Update workflow node mapping if part of a workflow
                if (!string.IsNullOrEmpty(rec.WorkflowId))
                {
                    var nodeId = await wfStore.GetNodeIdForTaskAsync(rec.WorkflowId, id);
                    if (!string.IsNullOrEmpty(nodeId))
                    {
                        await wfStore.SetNodeTaskMappingAsync(rec.WorkflowId, nodeId, newId);
                        await wfStore.ResetAttemptCountAsync(rec.WorkflowId, nodeId);
                    }
                }

                return Results.Ok(new { oldTaskId = id, newTaskId = newId, state = "Queued" });
            }

            // Get pending approvals for a workflow
            async Task<IResult> GetPendingApprovals(Orchestrator.Core.TaskLifecycle.ITaskStore store)
            {
                var tasks = await store.ListAsync();
                var pending = tasks.Where(t => t.State == TaskState.Pending)
                    .Select(t => new { id = t.Id, agentType = t.AgentType, prompt = t.Prompt, workflowId = t.WorkflowId, createdAt = t.CreatedAt });
                return Results.Json(pending);
            }

            // Workflow management endpoints: create workflow and start
            app.MapPost("/tasks", SubmitTask);
            app.MapGet("/tasks", ListTasks);
            app.MapPost("/workflows", CreateWorkflow);
            app.MapPost("/workflows/{id}/start", StartWorkflow);

            app.MapGet("/workflows", async (Orchestrator.Core.Workflow.IWorkflowStore store) =>
            {
                var list = await store.ListAsync();
                return Results.Json(list);
            });

            app.MapGet("/workflows/{id}/nodes", async (string id, Orchestrator.Core.Workflow.IWorkflowStore store) =>
            {
                var wf = await store.GetAsync(id);
                if (wf == null) return Results.NotFound();
                return Results.Json(wf.Nodes);
            });

            // Dynamic agent registration — register external webhook agents at runtime
            app.MapPost("/agents/register", async (HttpContext http, Orchestrator.Core.Agents.AgentRegistry registry) =>
            {
                using var sr = new StreamReader(http.Request.Body);
                var txt = await sr.ReadToEndAsync();
                var opts = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
                var body = JsonSerializer.Deserialize<JsonElement>(txt);
                var name = body.TryGetProperty("name", out var n) ? n.GetString()
                         : body.TryGetProperty("agentType", out var at) ? at.GetString() : null;
                var url = body.TryGetProperty("url", out var u) ? u.GetString() : null;
                if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(url))
                    return Results.BadRequest(new { error = "name and url are required" });
                // Register a webhook agent pointing at the given URL
                registry.Register(name, () =>
                {
                    Environment.SetEnvironmentVariable($"WEBHOOK_AGENT_URL_{name.ToUpperInvariant()}", url);
                    return new Orchestrator.Core.Agents.WebhookAgent();
                });
                return Results.Ok(new { registered = name, url });
            });

            app.MapGet("/agents", (Orchestrator.Core.Agents.AgentRegistry registry) =>
            {
                return Results.Json(registry.GetRegisteredAgents());
            });

            app.MapGet("/tasks/{id}", GetTaskById);
            app.MapPost("/tasks/{id}/cancel", CancelTask);
            app.MapPost("/tasks/{id}/restart", RestartTask);
            app.MapGet("/tasks/{id}/stream", StreamTaskSse);
            app.MapGet("/tasks/{id}/ws", StreamTaskWebSocket);
            app.MapGet("/workflows/{id}/stream", StreamWorkflowSse);
            app.MapPost("/workflows/{id}/nodes/{nodeId}/approve", ApproveNode);
            app.MapPost("/workflows/{id}/nodes/{nodeId}/reject", RejectNode);
            app.MapGet("/dashboard/approvals", GetPendingApprovals);

            // Versioned aliases
            app.MapPost("/api/v1/tasks", SubmitTask);
            app.MapGet("/api/v1/tasks", ListTasks);
            app.MapGet("/api/v1/tasks/{id}", GetTaskById);
            app.MapPost("/api/v1/tasks/{id}/cancel", CancelTask);
            app.MapPost("/api/v1/tasks/{id}/restart", RestartTask);
            app.MapGet("/api/v1/tasks/{id}/stream", StreamTaskSse);
            app.MapGet("/api/v1/tasks/{id}/ws", StreamTaskWebSocket);
            app.MapPost("/api/v1/workflows", CreateWorkflow);
            app.MapPost("/api/v1/workflows/{id}/start", StartWorkflow);
            app.MapGet("/api/v1/workflows/{id}/stream", StreamWorkflowSse);
            app.MapPost("/api/v1/workflows/{id}/nodes/{nodeId}/approve", ApproveNode);
            app.MapPost("/api/v1/workflows/{id}/nodes/{nodeId}/reject", RejectNode);
            app.MapGet("/api/v1/dashboard/approvals", GetPendingApprovals);
            app.MapGet("/api/v1/workflows", async (Orchestrator.Core.Workflow.IWorkflowStore store) =>
            {
                var list = await store.ListAsync();
                return Results.Json(list);
            });
            app.MapGet("/api/v1/workflows/{id}/nodes", async (string id, Orchestrator.Core.Workflow.IWorkflowStore store) =>
            {
                var wf = await store.GetAsync(id);
                if (wf == null) return Results.NotFound();
                return Results.Json(wf.Nodes);
            });

            app.MapGet("/", () => "Orchestrator API");

            await app.RunAsync();
        }
    }
}


