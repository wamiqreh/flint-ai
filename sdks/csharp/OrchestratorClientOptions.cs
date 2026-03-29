namespace Flint.AI.Sdk;

/// <summary>Configuration for <see cref="OrchestratorClient"/>.</summary>
public sealed class OrchestratorClientOptions
{
    /// <summary>Base URL of the orchestrator API (e.g. "http://localhost:5156").</summary>
    public string BaseUrl { get; set; } = "http://localhost:5156";

    /// <summary>Optional API key sent via the X-API-Key header.</summary>
    public string? ApiKey { get; set; }

    /// <summary>HTTP request timeout in seconds.</summary>
    public int TimeoutSeconds { get; set; } = 30;

    /// <summary>Maximum number of retries for transient failures.</summary>
    public int MaxRetries { get; set; } = 3;
}
