using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading.Tasks;

public class SubmitTask
{
    public static async Task Main(string[] args)
    {
        var client = new HttpClient { BaseAddress = new Uri("http://localhost:5000") };
        var payload = new { AgentType = "dummy", Prompt = "Reverse the string 'hello'" };
        var resp = await client.PostAsJsonAsync("/tasks", payload);
        resp.EnsureSuccessStatusCode();
        var body = await resp.Content.ReadFromJsonAsync<object>();
        Console.WriteLine("Submitted: " + System.Text.Json.JsonSerializer.Serialize(body));
    }
}