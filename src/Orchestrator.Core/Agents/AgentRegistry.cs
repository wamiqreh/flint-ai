using System;
using System.Collections.Concurrent;

namespace Orchestrator.Core.Agents
{
    public class AgentRegistry
    {
        private readonly ConcurrentDictionary<string, Func<object>> _map = new();

        public void Register(string name, Func<object> factory)
        {
            _map[name] = factory ?? throw new ArgumentNullException(nameof(factory));
        }

        public object Create(string name)
        {
            if (_map.TryGetValue(name, out var f)) return f();
            throw new InvalidOperationException($"Unknown agent: {name}");
        }

        public System.Collections.Generic.IEnumerable<string> GetRegisteredAgents()
        {
            return _map.Keys;
        }
    }
}