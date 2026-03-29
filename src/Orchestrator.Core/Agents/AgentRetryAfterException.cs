using System;

namespace Orchestrator.Core.Agents{    public class AgentRetryAfterException : Exception    {        public TimeSpan RetryAfter { get; }        public AgentRetryAfterException(string message, TimeSpan retryAfter)            : base(message)        {            RetryAfter = retryAfter;        }        public AgentRetryAfterException(string message, TimeSpan retryAfter, Exception inner)            : base(message, inner)        {            RetryAfter = retryAfter;        }    }}

