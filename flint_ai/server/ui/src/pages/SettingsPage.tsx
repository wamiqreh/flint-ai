import { useCallback } from 'react';
import { Server, Users, Heart, Activity, CheckCircle2, XCircle, ExternalLink } from 'lucide-react';
import { fetchAgents, fetchConcurrency, fetchHealth, type AgentInfo, type ConcurrencyInfo, type HealthStatus } from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { Card, ProgressBar, EmptyState, StatusBadge, LoadingState, ErrorAlert } from '../components/shared';

export default function SettingsPage() {
  const { data: agents, error: agentsErr, loading: agentsLoading } = usePolling<AgentInfo[]>(
    useCallback(() => fetchAgents(), []),
    10000
  );
  const { data: concurrency } = usePolling<ConcurrencyInfo>(
    useCallback(() => fetchConcurrency(), []),
    5000
  );
  const { data: health, error: healthErr } = usePolling<HealthStatus>(
    useCallback(() => fetchHealth(), []),
    10000
  );

  const isHealthy = health?.status === 'healthy';
  const isDegraded = health?.status === 'degraded';

  if (agentsLoading) return <LoadingState message="Loading settings..." />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Settings & Agents</h1>
        <p className="text-text-secondary text-sm mt-1">Server configuration and registered agents</p>
      </div>

      {agentsErr && <ErrorAlert message={agentsErr} />}

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

        {/* Server health */}
        <Card title="Server Health">
          <div className="space-y-3 text-sm">
            <div className={`flex items-center justify-between p-3 rounded-lg border ${
              healthErr ? 'bg-error/5 border-error/30' :
              isHealthy ? 'bg-success/5 border-success/30' :
              isDegraded ? 'bg-warning/5 border-warning/30' :
              'bg-surface border-border/50'
            }`}>
              <div className="flex items-center gap-2">
                <Heart className={`w-3.5 h-3.5 ${
                  healthErr ? 'text-error' : isHealthy ? 'text-success' : 'text-warning'
                }`} />
                <span>Overall Status</span>
              </div>
              <StatusBadge state={healthErr ? 'failed' : isHealthy ? 'succeeded' : 'pending'} />
            </div>
            {health?.checks && Object.entries(health.checks).map(([name, status]) => (
              <div key={name} className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
                <div className="flex items-center gap-2">
                  {status === 'ok' ?
                    <CheckCircle2 className="w-3.5 h-3.5 text-success" /> :
                    <XCircle className="w-3.5 h-3.5 text-error" />
                  }
                  <span className="capitalize">{name}</span>
                </div>
                <span className={`text-xs font-mono ${status === 'ok' ? 'text-success' : 'text-error'}`}>
                  {status}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* Server info */}
        <Card title="Server Info">
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">Engine</span>
              <span className="font-mono text-xs">Flint AI (FastAPI)</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">API Docs</span>
              <a href="/docs" target="_blank" className="text-accent hover:text-accent-hover text-xs inline-flex items-center gap-1">
                /docs <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">Metrics</span>
              <a href="/metrics" target="_blank" className="text-accent hover:text-accent-hover text-xs inline-flex items-center gap-1">
                /metrics <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg border border-border/50">
              <span className="text-text-secondary">Health Endpoint</span>
              <a href="/health" target="_blank" className="text-accent hover:text-accent-hover text-xs inline-flex items-center gap-1">
                /health <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
