import { useCallback, useState } from 'react';
import { DollarSign, BarChart3, TrendingUp, Search } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, PieChart, Pie,
} from 'recharts';
import {
  fetchCostSummary, fetchCostTimeline, fetchTasks,
  type CostSummary, type CostTimelinePoint, type Task,
} from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { Card, MetricCard, EmptyState, LoadingState, ErrorAlert } from '../components/shared';

const COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4', '#f97316', '#6b7280'];

export default function CostsPage() {
  const [search, setSearch] = useState('');
  const { data: costSummary, error: costErr, loading: costLoading, refresh: refreshCost } = usePolling<CostSummary>(
    useCallback(() => fetchCostSummary(), []),
    5000
  );
  const { data: timeline } = usePolling<CostTimelinePoint[]>(
    useCallback(() => fetchCostTimeline(24), []),
    10000
  );
  const { data: tasks } = usePolling<Task[]>(
    useCallback(() => fetchTasks(), []),
    5000
  );

  if (costLoading) return <LoadingState message="Loading cost data..." />;
  if (costErr) return <ErrorAlert message={costErr} onRetry={refreshCost} />;

  const costByModel = costSummary
    ? Object.entries(costSummary.by_model)
        .map(([name, d]) => ({ name, cost: d.cost_usd, tokens: d.tokens, count: d.count }))
        .sort((a, b) => b.cost - a.cost)
    : [];

  const costByAgent = costSummary
    ? Object.entries(costSummary.by_agent)
        .map(([name, d]) => ({ name, cost: d.cost_usd, tokens: d.tokens, count: d.count }))
        .sort((a, b) => b.cost - a.cost)
    : [];

  const tasksWithCost = (tasks ?? [])
    .filter(t => t.metadata?.cost_breakdown)
    .filter(t => !search || t.agent_type.toLowerCase().includes(search.toLowerCase()) || t.id.includes(search))
    .sort((a, b) => {
      const ca = (a.metadata?.cost_breakdown as any)?.total_cost_usd ?? 0;
      const cb = (b.metadata?.cost_breakdown as any)?.total_cost_usd ?? 0;
      return cb - ca;
    });

  const tokenDistribution = costByModel.map(m => ({
    name: m.name,
    prompt: Math.round(m.tokens * 0.67),
    completion: Math.round(m.tokens * 0.33),
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Costs</h1>
        <p className="text-text-secondary text-sm mt-1">Token usage and cost breakdown</p>
      </div>

      {/* Summary cards */}
      {costSummary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            label="Total Cost" value={`$${costSummary.total_cost_usd.toFixed(6)}`}
            icon={<DollarSign className="w-5 h-5" />} color="text-success"
          />
          <MetricCard
            label="Total Tokens" value={costSummary.total_tokens.toLocaleString()}
            icon={<BarChart3 className="w-5 h-5" />} color="text-info"
          />
          <MetricCard
            label="Tasks with Cost" value={costSummary.task_count}
            icon={<TrendingUp className="w-5 h-5" />} color="text-warning"
          />
          <MetricCard
            label="Avg Cost/Task"
            value={costSummary.task_count > 0 ? `$${(costSummary.total_cost_usd / costSummary.task_count).toFixed(6)}` : '$0'}
            icon={<DollarSign className="w-5 h-5" />} color="text-primary"
          />
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Cost by Model">
          {costByModel.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={costByModel} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `$${v.toFixed(4)}`} />
                <Tooltip
                  contentStyle={{ background: '#1e2231', border: '1px solid #2a2e3d', borderRadius: '8px', fontSize: '12px' }}
                  formatter={(value: any, name: any) => {
                    if (name === 'cost') return [`$${Number(value).toFixed(6)}`, 'Cost'];
                    return [Number(value).toLocaleString(), 'Tokens'];
                  }}
                />
                <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
                  {costByModel.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={<DollarSign className="w-8 h-8" />} message="No cost data" />
          )}
        </Card>

        <Card title="Cost Over Time (24h)">
          {timeline && timeline.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={timeline} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
                <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false}
                  tickFormatter={(v: string) => v.slice(11, 16)} />
                <YAxis tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `$${v.toFixed(4)}`} />
                <Tooltip
                  contentStyle={{ background: '#1e2231', border: '1px solid #2a2e3d', borderRadius: '8px', fontSize: '12px' }}
                  formatter={(value: any) => [`$${Number(value).toFixed(6)}`, 'Cost']}
                />
                <Line type="monotone" dataKey="cost_usd" stroke="#22c55e" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={<TrendingUp className="w-8 h-8" />} message="No timeline data" />
          )}
        </Card>

        <Card title="Cost by Agent">
          {costByAgent.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={costByAgent} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `$${v.toFixed(4)}`} />
                <Tooltip
                  contentStyle={{ background: '#1e2231', border: '1px solid #2a2e3d', borderRadius: '8px', fontSize: '12px' }}
                  formatter={(value: any) => [`$${Number(value).toFixed(6)}`, 'Cost']}
                />
                <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
                  {costByAgent.map((_, i) => <Cell key={i} fill={COLORS[(i + 3) % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={<DollarSign className="w-8 h-8" />} message="No agent cost data" />
          )}
        </Card>

        <Card title="Token Distribution (Prompt vs Completion)">
          {tokenDistribution.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={tokenDistribution} cx="50%" cy="50%" innerRadius={50} outerRadius={90}
                  paddingAngle={2} dataKey="tokens" nameKey="name" stroke="none">
                  {tokenDistribution.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#1e2231', border: '1px solid #2a2e3d', borderRadius: '8px', fontSize: '12px' }}
                  itemStyle={{ color: '#e4e6ed' }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={<BarChart3 className="w-8 h-8" />} message="No token data" />
          )}
        </Card>
      </div>

      {/* Task cost table */}
      <Card title="Task Costs">
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
            <input
              type="text"
              placeholder="Filter by agent or task ID..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-surface-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
        </div>
        {tasksWithCost.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-secondary text-xs uppercase tracking-wider border-b border-border">
                  <th className="text-left py-2 px-3">Task ID</th>
                  <th className="text-left py-2 px-3">Agent</th>
                  <th className="text-left py-2 px-3">Model</th>
                  <th className="text-right py-2 px-3">Prompt Tokens</th>
                  <th className="text-right py-2 px-3">Completion Tokens</th>
                  <th className="text-right py-2 px-3">Total Tokens</th>
                  <th className="text-right py-2 px-3">Cost (USD)</th>
                  <th className="text-left py-2 px-3">State</th>
                </tr>
              </thead>
              <tbody>
                {tasksWithCost.map(t => {
                  const cb = t.metadata?.cost_breakdown as any;
                  return (
                    <tr key={t.id} className="border-b border-border/50 hover:bg-surface-3/50">
                      <td className="py-2 px-3 font-mono text-xs">{t.id.slice(0, 8)}</td>
                      <td className="py-2 px-3">{t.agent_type}</td>
                      <td className="py-2 px-3 text-text-secondary">{cb?.model ?? '—'}</td>
                      <td className="py-2 px-3 text-right">{cb?.prompt_tokens?.toLocaleString() ?? 0}</td>
                      <td className="py-2 px-3 text-right">{cb?.completion_tokens?.toLocaleString() ?? 0}</td>
                      <td className="py-2 px-3 text-right font-medium">{cb?.total_tokens?.toLocaleString() ?? 0}</td>
                      <td className="py-2 px-3 text-right text-success font-medium">${cb?.total_cost_usd?.toFixed(6) ?? '0.000000'}</td>
                      <td className="py-2 px-3">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                          t.state === 'succeeded' ? 'bg-success/10 text-success' :
                          t.state === 'failed' ? 'bg-error/10 text-error' :
                          'bg-warning/10 text-warning'
                        }`}>
                          {t.state}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={<DollarSign className="w-8 h-8" />} message="No tasks with cost data" />
        )}
      </Card>
    </div>
  );
}
