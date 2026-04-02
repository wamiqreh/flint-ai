import { useCallback } from 'react';
import {
  BarChart3,
  Activity,
  Clock,
  AlertTriangle,
  Layers,
  Users,
  CheckCircle2,
  XCircle,
  TrendingUp,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie,
} from 'recharts';
import { fetchSummary, fetchConcurrency, fetchApprovals, type DashboardSummary, type ConcurrencyInfo, type Task } from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { MetricCard, Card, ProgressBar, Button, EmptyState, LoadingState, ErrorAlert } from '../components/shared';
import { approveTask, rejectTask } from '../lib/api';
import { useToast } from '../components/Toast';

const STATE_COLORS: Record<string, string> = {
  queued: '#f59e0b', running: '#3b82f6', succeeded: '#22c55e',
  failed: '#ef4444', dead_letter: '#a855f7', pending: '#f97316', cancelled: '#6b7280',
};

export default function DashboardPage() {
  const { toast } = useToast();
  const { data: summary, error: summaryErr, loading: summaryLoading, refresh: refreshSummary } = usePolling<DashboardSummary>(
    useCallback(() => fetchSummary(), []),
    3000
  );
  const { data: concurrency, error: concurrencyErr } = usePolling<ConcurrencyInfo>(
    useCallback(() => fetchConcurrency(), []),
    3000
  );
  const { data: approvals, refresh: refreshApprovals } = usePolling<Task[]>(
    useCallback(() => fetchApprovals(), []),
    5000
  );

  const byState = summary?.by_state ?? {};
  const pieData = Object.entries(byState)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }));

  const successRate = summary?.total
    ? Math.round(((byState.succeeded ?? 0) / summary.total) * 100)
    : 0;

  const handleApprove = async (id: string) => {
    try {
      await approveTask(id);
      toast('success', 'Task approved');
      refreshApprovals();
    } catch (e) {
      toast('error', `Failed to approve: ${e instanceof Error ? e.message : 'Unknown error'}`);
    }
  };
  const handleReject = async (id: string) => {
    try {
      await rejectTask(id);
      toast('warning', 'Task rejected');
      refreshApprovals();
    } catch (e) {
      toast('error', `Failed to reject: ${e instanceof Error ? e.message : 'Unknown error'}`);
    }
  };

  if (summaryLoading) return <LoadingState message="Loading dashboard..." />;
  if (summaryErr) return <ErrorAlert message={summaryErr} onRetry={refreshSummary} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-text-secondary text-sm mt-1">Real-time orchestrator overview</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
          Live — polling every 3s
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <MetricCard
          label="Total Tasks" value={summary?.total ?? 0}
          icon={<Layers className="w-5 h-5" />}
          sub={`${byState.succeeded ?? 0} succeeded, ${byState.failed ?? 0} failed`}
        />
        <MetricCard
          label="Active" value={(byState.running ?? 0) + (byState.queued ?? 0)}
          icon={<Activity className="w-5 h-5" />} color="text-info"
          sub={`${byState.running ?? 0} running, ${byState.queued ?? 0} queued`}
        />
        <MetricCard
          label="Queue Depth" value={summary?.queue_length ?? 0}
          icon={<Clock className="w-5 h-5" />} color="text-warning"
        />
        <MetricCard
          label="Dead Letters" value={summary?.dlq_length ?? 0}
          icon={<AlertTriangle className="w-5 h-5" />} color="text-error"
          trend={summary?.dlq_length ? 'up' : 'neutral'}
        />
        <MetricCard
          label="Success Rate" value={`${successRate}%`}
          icon={<TrendingUp className="w-5 h-5" />} color="text-success"
          trend={successRate >= 90 ? 'up' : successRate >= 50 ? 'neutral' : 'down'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Task distribution pie */}
        <Card title="Task Distribution">
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80}
                  paddingAngle={2} dataKey="value" stroke="none">
                  {pieData.map((entry) => (
                    <Cell key={entry.name} fill={STATE_COLORS[entry.name] ?? '#6b7280'} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#1e2231', border: '1px solid #2a2e3d', borderRadius: '8px', fontSize: '12px' }}
                  itemStyle={{ color: '#e4e6ed' }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={<BarChart3 className="w-8 h-8" />} message="No tasks yet" />
          )}
          <div className="flex flex-wrap gap-3 mt-2 justify-center">
            {pieData.map(({ name, value }) => (
              <div key={name} className="flex items-center gap-1.5 text-xs">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: STATE_COLORS[name] }} />
                <span className="text-text-secondary capitalize">{name.replace('_', ' ')}</span>
                <span className="font-medium">{value}</span>
              </div>
            ))}
          </div>
        </Card>

        {/* State breakdown bar chart */}
        <Card title="Tasks by State">
          {Object.keys(byState).length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={Object.entries(byState).map(([state, count]) => ({ state, count }))}
                margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
                <XAxis dataKey="state" tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: '#1e2231', border: '1px solid #2a2e3d', borderRadius: '8px', fontSize: '12px' }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {Object.entries(byState).map(([state]) => (
                    <Cell key={state} fill={STATE_COLORS[state] ?? '#6b7280'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={<BarChart3 className="w-8 h-8" />} message="No data" />
          )}
        </Card>

        {/* Agent concurrency */}
        <Card title="Agent Concurrency">
          {concurrencyErr ? (
            <ErrorAlert message="Failed to load concurrency data" />
          ) : concurrency && Object.keys(concurrency).length > 0 ? (
            <div className="space-y-4">
              {Object.entries(concurrency).map(([agent, { limit, used }]) => (
                <div key={agent}>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-medium flex items-center gap-1.5">
                      <Users className="w-3.5 h-3.5 text-text-secondary" />
                      {agent}
                    </span>
                    <span className="text-xs text-text-secondary">{used}/{limit}</span>
                  </div>
                  <ProgressBar value={used} max={limit} />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState icon={<Users className="w-8 h-8" />} message="No agents registered" />
          )}
        </Card>
      </div>

      {/* Pending approvals */}
      {approvals && approvals.length > 0 && (
        <Card title={`Pending Approvals (${approvals.length})`}
          actions={<span className="text-xs text-warning">⚡ Requires action</span>}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-secondary text-xs uppercase tracking-wider border-b border-border">
                  <th className="text-left py-2 px-3">Task ID</th>
                  <th className="text-left py-2 px-3">Agent</th>
                  <th className="text-left py-2 px-3">Prompt</th>
                  <th className="text-left py-2 px-3">Workflow</th>
                  <th className="text-right py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {approvals.map((t) => (
                  <tr key={t.id} className="border-b border-border/50 hover:bg-surface-3/50">
                    <td className="py-2 px-3 font-mono text-xs">{t.id.slice(0, 8)}</td>
                    <td className="py-2 px-3">{t.agent_type}</td>
                    <td className="py-2 px-3 max-w-xs truncate">{t.prompt}</td>
                    <td className="py-2 px-3 text-text-secondary">{t.workflow_id ?? '—'}</td>
                    <td className="py-2 px-3 text-right space-x-2">
                      <Button variant="primary" size="xs" onClick={() => handleApprove(t.id)}>
                        <CheckCircle2 className="w-3 h-3" /> Approve
                      </Button>
                      <Button variant="danger" size="xs" onClick={() => handleReject(t.id)}>
                        <XCircle className="w-3 h-3" /> Reject
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
