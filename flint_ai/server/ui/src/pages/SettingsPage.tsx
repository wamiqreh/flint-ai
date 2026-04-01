import { useCallback } from 'react';
import { Server, Users, Heart, Activity } from 'lucide-react';
import { fetchAgents, fetchConcurrency, type AgentInfo, type ConcurrencyInfo } from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { Card, ProgressBar, EmptyState, StatusBadge } from '../components/shared';

export default function SettingsPage() {
  const { data: agents } = usePolling<AgentInfo[]>(
    useCallback(() => fetchAgents(), []),
    10000
  );
  const { data: concurrency } = usePolling<ConcurrencyInfo>(
    useCallback(() => fetchConcurrency(), []),
    5000
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings & Agents</h1>
        <p className="text-text-secondary text-sm mt-1">Server configuration and registered agents</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Registered agents */}
        <Card title="Registered Agents" actions={
          <span className="text-xs text-text-secondary">{agents?.length ?? 0} agents</span>
        }>
          {agents && agents.length > 0 ? (
            <div className="space-y-3">
              {agents.map((a) => (
                <div key={a.agent_type} className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                      a.healthy ? 'bg-success/10 text-success' : 'bg-error/10 text-error'
                    }`}>
                      <Server className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="font-medium text-sm">{a.agent_type}</p>
                      <p className="text-[10px] text-text-secondary">
                        {a.healthy ? 'Healthy' : 'Unhealthy'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${a.healthy ? 'bg-success' : 'bg-error'}`} />
                    <StatusBadge state={a.healthy ? 'succeeded' : 'failed'} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={<Users className="w-8 h-8" />} message="No agents registered" />
          )}
        </Card>

        {/* Concurrency config */}
        <Card title="Concurrency Limits">
          {concurrency && Object.keys(concurrency).length > 0 ? (
            <div className="space-y-4">
              {Object.entries(concurrency).map(([agent, { limit, used }]) => (
                <div key={agent} className="p-3 bg-surface rounded-lg border border-border/50">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Activity className="w-3.5 h-3.5 text-text-secondary" />
                      <span className="font-medium text-sm">{agent}</span>
                    </div>
                    <span className="text-xs font-mono">
                      <span className={used > limit * 0.8 ? 'text-error' : used > limit * 0.5 ? 'text-warning' : 'text-success'}>
                        {used}
                      </span>
                      <span className="text-text-secondary"> / {limit}</span>
                    </span>
                  </div>
                  <ProgressBar value={used} max={limit} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={<Activity className="w-8 h-8" />} message="No concurrency data" />
          )}
        </Card>

        {/* Server info */}
        <Card title="Server Info">
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <div className="flex items-center gap-2">
                <Heart className="w-3.5 h-3.5 text-success" />
                <span>Health</span>
              </div>
              <StatusBadge state="succeeded" />
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">Version</span>
              <span className="font-mono text-xs">1.0.0</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">Engine</span>
              <span className="font-mono text-xs">Flint Python Server (FastAPI)</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">API Docs</span>
              <a href="/docs" target="_blank" className="text-accent hover:text-accent-hover text-xs">
                /docs (Swagger)
              </a>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">Metrics</span>
              <a href="/metrics" target="_blank" className="text-accent hover:text-accent-hover text-xs">
                /metrics (Prometheus)
              </a>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
