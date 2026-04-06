import { useCallback, useState } from 'react';
import { Search, ChevronRight, ChevronDown, AlertCircle, CheckCircle2, Clock, DollarSign, Copy, X } from 'lucide-react';
import {
  fetchToolExecutions, fetchToolErrors, fetchToolStats,
  type ToolExecution, type ToolStats,
} from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { Card, MetricCard, EmptyState, LoadingState, ErrorAlert } from '../components/shared';

function formatDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function getStatusColor(status: string): string {
  if (status === 'succeeded') return 'text-success';
  if (status === 'failed') return 'text-error';
  return 'text-warning';
}

function getStatusBg(status: string): string {
  if (status === 'succeeded') return 'bg-success/10';
  if (status === 'failed') return 'bg-error/10';
  return 'bg-warning/10';
}

function ErrorDetailModal({ execution, onClose }: { execution: ToolExecution; onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  const copyStackTrace = () => {
    navigator.clipboard.writeText(execution.stack_trace ?? execution.error ?? '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-surface-2 border border-border rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden m-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-error" />
            <h2 className="text-lg font-semibold">Tool Error: {execution.tool_name}</h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-surface-3 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto max-h-[calc(80vh-80px)]">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-text-secondary text-xs">Tool</span>
              <p className="font-mono">{execution.tool_name}</p>
            </div>
            <div>
              <span className="text-text-secondary text-xs">Status</span>
              <p className="font-medium text-error">{execution.status}</p>
            </div>
            <div>
              <span className="text-text-secondary text-xs">Task ID</span>
              <p className="font-mono text-xs">{execution.task_id}</p>
            </div>
            <div>
              <span className="text-text-secondary text-xs">Node ID</span>
              <p className="font-mono text-xs">{execution.node_id ?? '—'}</p>
            </div>
            <div>
              <span className="text-text-secondary text-xs">Duration</span>
              <p>{formatDuration(execution.duration_ms)}</p>
            </div>
            <div>
              <span className="text-text-secondary text-xs">Timestamp</span>
              <p className="text-xs">{new Date(execution.created_at).toLocaleString()}</p>
            </div>
          </div>

          {execution.error && (
            <div>
              <span className="text-text-secondary text-xs">Error Message</span>
              <pre className="mt-1 p-3 bg-error/5 border border-error/20 rounded-lg text-sm text-error font-mono overflow-x-auto">
                {execution.error}
              </pre>
            </div>
          )}

          {execution.stack_trace && (
            <div>
              <div className="flex items-center justify-between">
                <span className="text-text-secondary text-xs">Stack Trace</span>
                <button
                  onClick={copyStackTrace}
                  className="flex items-center gap-1 text-xs text-text-secondary hover:text-text-primary transition-colors"
                >
                  <Copy className="w-3 h-3" />
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <pre className="mt-1 p-3 bg-surface-3 border border-border rounded-lg text-xs font-mono overflow-x-auto max-h-60">
                {execution.stack_trace}
              </pre>
            </div>
          )}

          {execution.sanitized_input && (
            <div>
              <span className="text-text-secondary text-xs">Sanitized Input</span>
              <pre className="mt-1 p-3 bg-surface-3 border border-border rounded-lg text-xs font-mono overflow-x-auto max-h-40">
                {JSON.stringify(execution.sanitized_input, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ToolCallRow({ execution, depth = 0 }: { execution: ToolExecution; depth?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [showErrorModal, setShowErrorModal] = useState(false);

  const isSlow = (execution.duration_ms ?? 0) > 1000;

  return (
    <>
      <div
        className={`flex items-center gap-2 py-2 px-3 border-b border-border/50 hover:bg-surface-3/50 cursor-pointer transition-colors ${
          depth > 0 ? 'pl-' + (depth * 4 + 3) : ''
        }`}
        style={{ paddingLeft: `${depth * 16 + 12}px` }}
        onClick={() => setExpanded(!expanded)}
      >
        <button className="p-0.5 hover:bg-surface-3 rounded transition-colors">
          {expanded ? <ChevronDown className="w-3.5 h-3.5 text-text-secondary" /> : <ChevronRight className="w-3.5 h-3.5 text-text-secondary" />}
        </button>

        {execution.status === 'succeeded' ? (
          <CheckCircle2 className={`w-4 h-4 ${isSlow ? 'text-warning' : 'text-success'}`} />
        ) : (
          <AlertCircle className="w-4 h-4 text-error" />
        )}

        <span className="text-sm font-medium flex-1">{execution.tool_name}</span>

        <span className="flex items-center gap-1 text-xs text-text-secondary">
          <Clock className="w-3 h-3" />
          {formatDuration(execution.duration_ms)}
        </span>

        {execution.cost_usd > 0 && (
          <span className="flex items-center gap-1 text-xs text-success">
            <DollarSign className="w-3 h-3" />
            ${execution.cost_usd.toFixed(6)}
          </span>
        )}

        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${getStatusBg(execution.status)} ${getStatusColor(execution.status)}`}>
          {execution.status}
        </span>
      </div>

      {expanded && (
        <div className="bg-surface-3/50 border-b border-border/50 px-4 py-3 text-xs space-y-2" style={{ paddingLeft: `${depth * 16 + 28}px` }}>
          {execution.input_json && (
            <div>
              <span className="text-text-secondary">Input:</span>
              <pre className="mt-1 p-2 bg-surface-2 border border-border rounded font-mono overflow-x-auto max-h-32">
                {JSON.stringify(execution.input_json, null, 2)}
              </pre>
            </div>
          )}
          {execution.output_json && (
            <div>
              <span className="text-text-secondary">Output:</span>
              <pre className="mt-1 p-2 bg-surface-2 border border-border rounded font-mono overflow-x-auto max-h-32">
                {typeof execution.output_json === 'string' ? execution.output_json : JSON.stringify(execution.output_json, null, 2)}
              </pre>
            </div>
          )}
          {execution.error && (
            <button
              onClick={(e) => { e.stopPropagation(); setShowErrorModal(true); }}
              className="flex items-center gap-1 text-error hover:underline"
            >
              <AlertCircle className="w-3 h-3" />
              View error details
            </button>
          )}
          <div className="text-text-secondary">
            Task: <span className="font-mono">{execution.task_id.slice(0, 8)}</span>
            {execution.workflow_run_id && <> | Run: <span className="font-mono">{execution.workflow_run_id.slice(0, 8)}</span></>}
            {execution.node_id && <> | Node: <span className="font-mono">{execution.node_id}</span></>}
          </div>
        </div>
      )}

      {showErrorModal && <ErrorDetailModal execution={execution} onClose={() => setShowErrorModal(false)} />}
    </>
  );
}

export default function ToolTracePage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [workflowRunId, setWorkflowRunId] = useState('');

  const { data: executions, error: execErr, loading: execLoading, refresh: refreshExec } = usePolling<ToolExecution[]>(
    useCallback(() => {
      const params: Record<string, string | number> = { limit: 200 };
      if (workflowRunId) params.workflow_run_id = workflowRunId;
      return fetchToolExecutions(params);
    }, [workflowRunId]),
    5000
  );

  const { data: errors } = usePolling<ToolExecution[]>(
    useCallback(() => fetchToolErrors({ limit: 50 }), []),
    10000
  );

  const { data: stats } = usePolling<ToolStats>(
    useCallback(() => fetchToolStats(), []),
    10000
  );

  if (execLoading) return <LoadingState message="Loading tool executions..." />;
  if (execErr) return <ErrorAlert message={execErr} onRetry={refreshExec} />;

  const filtered = (executions ?? [])
    .filter(e => statusFilter === 'all' || e.status === statusFilter)
    .filter(e => !search || e.tool_name.toLowerCase().includes(search.toLowerCase()) || e.task_id.includes(search));

  const groupedByWorkflow = filtered.reduce<Record<string, ToolExecution[]>>((acc, e) => {
    const key = e.workflow_run_id || 'standalone';
    if (!acc[key]) acc[key] = [];
    acc[key].push(e);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Tool Trace</h1>
        <p className="text-text-secondary text-sm mt-1">Detailed tool execution trace and error reporting</p>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard
            label="Total Executions" value={stats.total_executions}
            icon={<Clock className="w-5 h-5" />} color="text-info"
          />
          <MetricCard
            label="Errors" value={stats.error_count}
            icon={<AlertCircle className="w-5 h-5" />} color="text-error"
          />
          <MetricCard
            label="Error Rate" value={`${(stats.error_rate * 100).toFixed(1)}%`}
            icon={<AlertCircle className="w-5 h-5" />} color={stats.error_rate > 0.1 ? 'text-error' : 'text-success'}
          />
          <MetricCard
            label="Tools Used" value={Object.keys(stats.by_tool).length}
            icon={<Search className="w-5 h-5" />} color="text-warning"
          />
        </div>
      )}

      {/* Filters */}
      <Card title="Filters">
        <div className="flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
            <input
              type="text"
              placeholder="Filter by tool name or task ID..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-surface-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-surface-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            <option value="all">All Status</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
          </select>
          <input
            type="text"
            placeholder="Workflow run ID..."
            value={workflowRunId}
            onChange={e => setWorkflowRunId(e.target.value)}
            className="px-3 py-2 bg-surface-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 min-w-[200px]"
          />
        </div>
      </Card>

      {/* Tool execution tree */}
      <Card title={`Tool Executions (${filtered.length})`}>
        {filtered.length > 0 ? (
          <div className="border border-border rounded-lg overflow-hidden">
            {Object.entries(groupedByWorkflow).map(([wfId, execs]) => (
              <div key={wfId}>
                <div className="px-4 py-2 bg-surface-3 border-b border-border text-xs font-medium text-text-secondary">
                  {wfId === 'standalone' ? 'Standalone Tasks' : `Workflow Run: ${wfId.slice(0, 8)}`}
                  <span className="ml-2 text-text-secondary">({execs.length} calls)</span>
                </div>
                {execs.map(e => (
                  <ToolCallRow key={e.id} execution={e} />
                ))}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Clock className="w-8 h-8" />} message="No tool executions found" />
        )}
      </Card>

      {/* Recent errors */}
      {errors && errors.length > 0 && (
        <Card title={`Recent Errors (${errors.length})`}
          actions={<span className="text-xs text-error">Requires attention</span>}>
          <div className="space-y-2">
            {errors.slice(0, 10).map(e => (
              <ErrorDetailCard key={e.id} execution={e} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function ErrorDetailCard({ execution }: { execution: ToolExecution }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-error/20 rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 p-3 bg-error/5 cursor-pointer hover:bg-error/10 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <AlertCircle className="w-4 h-4 text-error shrink-0" />
        <span className="font-mono text-sm font-medium">{execution.tool_name}</span>
        <span className="text-xs text-text-secondary flex-1 truncate">{execution.error}</span>
        <span className="text-xs text-text-secondary">{formatDuration(execution.duration_ms)}</span>
        <ChevronRight className={`w-4 h-4 text-text-secondary transition-transform ${expanded ? 'rotate-90' : ''}`} />
      </div>
      {expanded && (
        <div className="p-3 bg-surface-3 space-y-2 text-xs">
          <div className="text-text-secondary">
            Task: <span className="font-mono">{execution.task_id}</span>
            {execution.node_id && <> | Node: <span className="font-mono">{execution.node_id}</span></>}
          </div>
          {execution.stack_trace && (
            <pre className="p-2 bg-surface-2 border border-border rounded font-mono overflow-x-auto max-h-40">
              {execution.stack_trace}
            </pre>
          )}
          {execution.sanitized_input && (
            <div>
              <span className="text-text-secondary">Input:</span>
              <pre className="mt-1 p-2 bg-surface-2 border border-border rounded font-mono overflow-x-auto max-h-32">
                {JSON.stringify(execution.sanitized_input, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
