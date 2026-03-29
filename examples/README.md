Examples

C# example

- examples/csharp/SubmitTask.cs - simple .NET console app that POSTs a task to the API.

Run:
- dotnet run --project examples/csharp/SubmitTask.csproj (not provided; compile as a small console app or run as a script with dotnet-script)

Python example

- examples/python/submit_task.py
- sdks/python/examples/quickstart.py
- sdks/python/examples/workflow_example.py
- sdks/python/examples/streaming_example.py
- sdks/python/examples/batch_processing.py

Run:
- python examples/python/submit_task.py "Say hello"
- cd sdks/python && pip install . && python examples/quickstart.py

Notes
- Ensure the API is running (dotnet run --project src/Orchestrator.Api --urls "http://localhost:5000")
- These are minimal examples for onboarding and can be expanded into SDK wrappers.
