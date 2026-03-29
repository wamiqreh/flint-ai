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
                builder.Services.AddSingleton<IWorkflowStore>(_ => new PostgresWorkflowStore());
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
                try { registry.Register("copilot", () => new Orchestrator.Core.Agents.CopilotAgent()); } catch { }
                try { registry.Register("claude", () => new Orchestrator.Core.Agents.ClaudeAgent()); } catch { }
                if (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("OPENAI_API_KEY")))
                {
                    registry.Register("openai", () => new Orchestrator.Core.Agents.OpenAiAgent());
                }
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
                    var def = JsonSerializer.Deserialize<WorkflowDefinition>(body.GetRawText());
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
                    var rec = new TaskRecord(newId, node.AgentType, node.PromptTemplate, def.Id, TaskState.Queued, null, DateTimeOffset.UtcNow);
                    await engine.EnqueueTaskAsync(rec);
                    await store.SetNodeTaskMappingAsync(def.Id, node.Id, newId);
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
                http.Response.Headers["Content-Type"] = "text/event-stream";
                http.Response.Headers["Cache-Control"] = "no-cache";
                http.Response.Headers["Connection"] = "keep-alive";

                string lastPayload = null;
                while (!http.RequestAborted.IsCancellationRequested)
                {
                    TaskRecord rec;
                    try
                    {
                        rec = await store.GetAsync(id, http.RequestAborted);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }

                    if (rec == null)
                    {
                        var notFoundPayload = JsonSerializer.Serialize(new { id, state = "NotFound", result = (string)null, workflowId = (string)null });
                        await http.Response.WriteAsync($"event: not_found\ndata: {notFoundPayload}\n\n", http.RequestAborted);
                        await http.Response.Body.FlushAsync(http.RequestAborted);
                        break;
                    }

                    var payload = JsonSerializer.Serialize(new { id = rec.Id, state = rec.State.ToString(), result = rec.ResultJson, workflowId = rec.WorkflowId });
                    if (!string.Equals(payload, lastPayload, StringComparison.Ordinal))
                    {
                        await http.Response.WriteAsync($"event: update\ndata: {payload}\n\n", http.RequestAborted);
                        await http.Response.Body.FlushAsync(http.RequestAborted);
                        lastPayload = payload;
                    }

                    if (rec.State == TaskState.Succeeded || rec.State == TaskState.Failed || rec.State == TaskState.DeadLetter)
                    {
                        await http.Response.WriteAsync($"event: complete\ndata: {payload}\n\n", http.RequestAborted);
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

            // Workflow management endpoints: create workflow and start
            app.MapPost("/tasks", SubmitTask);
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

            app.MapGet("/tasks/{id}", GetTaskById);
            app.MapGet("/tasks/{id}/stream", StreamTaskSse);
            app.MapGet("/tasks/{id}/ws", StreamTaskWebSocket);

            // Versioned aliases
            app.MapPost("/api/v1/tasks", SubmitTask);
            app.MapGet("/api/v1/tasks/{id}", GetTaskById);
            app.MapGet("/api/v1/tasks/{id}/stream", StreamTaskSse);
            app.MapGet("/api/v1/tasks/{id}/ws", StreamTaskWebSocket);
            app.MapPost("/api/v1/workflows", CreateWorkflow);
            app.MapPost("/api/v1/workflows/{id}/start", StartWorkflow);
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


