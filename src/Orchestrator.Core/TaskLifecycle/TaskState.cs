using System;


namespace Orchestrator.Core.TaskLifecycle
{
    public enum TaskState
    {
        Pending,
        Queued,
        Running,
        Succeeded,
        Failed,
        DeadLetter
    }
}
