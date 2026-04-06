import { useState, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Clock,
  CheckCircle2,
  AlertCircle,
  ChevronRight,
  DollarSign,
  Wrench,
  Layers,
  Timer,
  Search,
  RefreshCw,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import {
  fetchWorkflows, fetchWorkflowRuns, fetchWorkflow, fetchTasks,
  fetchToolExecutions,
  type WorkflowDef, type WorkflowRun, type Task, type ToolExecution,
} from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { Card, MetricCard, EmptyState, LoadingState, ErrorAlert, StatusBadge } from '../components/shared';

const COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4'];

function formatDuration(seconds: number): string {
  if (seconds <= 0) return '—';
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

function stateColor(state: string): string {
  if (state === 'succeeded' || state === 'completed') return 'text-success';
  if (state === 'failed' || state === 'dead_letter') return 'text-error';
  if (state === 'running') return 'text-info';
  return 'text-warning';
}

function stateBg(state: string): string {
  if (state === 'succeeded' || state === 'completed') return 'bg-success/10';
  if (state === 'failed' || state === 'dead_letter') return 'bg-error/10';
  if (state === 'running') return 'bg-info/10';
  return 'bg-warning/10';
}

export default function RunsPage() {
  const [search, setSearch] = useState('');
  const [selectedWf, setSelectedWf] = useState<WorkflowDef | null>(null);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [wfDef, setWfDef] = useState<WorkflowDef | null>(null);

  const { data: workflows, error: wfErr, loading: wfLoading } = usePolling<WorkflowDef[]>(
    useCallback(() => fetchWorkflows(), []),
    5000
  );

  const { data: tasks } = usePolling<Task[]>(
    useCallback(() => fetchTasks(), []),
    3000
  );

  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);

  const loadRuns = useCallback(async (wfId: string) => {
    setRunsLoading(true);
    try {
      const data = await fetchWorkflowRuns(wfId);
      setRuns(data);
    } catch {
      setRuns([]);
    } finally {
      setRunsLoading(false);
    }
  }, []);

  const handleWfClick = async (wf: WorkflowDef) => {
    if (selectedWf?.id === wf.id) {
      setSelectedWf(null);
      setSelectedRun(null);
      setRuns([]);
    } else {
      setSelectedWf(wf);
      setSelectedRun(null);
      setRuns([]);
      await loadRuns(wf.id);
    }
  };

  const handleRunClick = async (run: WorkflowRun) => {
    if (selectedRun?.id === run.id) {
      setSelectedRun(null);
    } else {
      setSelectedRun(run);
      if (!wfDef || wfDef.id !== run.workflow_id) {
        try {
          const wf = await fetchWorkflow(run.workflow_id);
          setWfDef(wf);
        } catch { /* ignore */ }
      }
    }
  };

  if (wfLoading) return <LoadingState message="Loading workflows..." />;
  if (wfErr) return <ErrorAlert message={wfErr} />;

  const filteredWorkflows = (workflows ?? [])
    .filter(wf => !search || wf.id.toLowerCase().includes(search.toLowerCase()) || (wf.name ?? '').toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Workflow Runs</h1>
        <p className="text-text-secondary text-sm mt-1">Click a workflow to see runs, tasks, tools, and costs</p>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
        <input
          type="text"
          placeholder="Search workflows..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-surface-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
        />
      </div>

      {/* Workflow grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredWorkflows.map(wf => (
          <WorkflowCard
            key={wf.id}
            workflow={wf}
            tasks={tasks ?? []}
            runs={runs}
            runsLoading={runsLoading}
            isSelected={selectedWf?.id === wf.id}
            onClick={() => handleWfClick(wf)}
            onLoadRuns={() => loadRuns(wf.id)}
          />
        ))}
        {filteredWorkflows.length === 0 && (
          <div className="col-span-full">
            <EmptyState icon={<Layers className="w-8 h-8" />} message="No workflows found" />
          </div>
        )}
      </div>

      {/* Runs list for selected workflow */}
      {selectedWf && runs.length > 0 && (
        <Card title={`Runs for: ${selectedWf.name || selectedWf.id} (${runs.length})`}>
          <div className="space-y-2">
            {runs.map(run => (
              <div
                key={run.id}
                className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                  selectedRun?.id === run.id
                    ? 'bg-primary/10 border border-primary/30'
                    : 'bg-surface-2 hover:bg-surface-3 border border-transparent'
                }`}
                onClick={() => handleRunClick(run)}
              >
                <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                  run.state === 'completed' || run.state === 'succeeded' ? 'bg-success' :
                  run.state === 'failed' ? 'bg-error' :
                  run.state === 'running' ? 'bg-info animate-pulse' :
                  'bg-warning'
                }`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-mono truncate">{run.id}</p>
                  <p className="text-xs text-text-secondary">
                    {new Date(run.started_at).toLocaleString()}
                    {run.completed_at && ` → ${new Date(run.completed_at).toLocaleString()}`}
                  </p>
                </div>
                <span className={`text-xs font-medium capitalize ${stateColor(run.state)}`}>
                  {run.state}
                </span>
                <ChevronRight className={`w-4 h-4 text-text-secondary transition-transform ${selectedRun?.id === run.id ? 'rotate-90' : ''}`} />
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Run detail */}
      {selectedRun && (
        <RunDetail run={selectedRun} wfDef={wfDef || selectedWf} tasks={tasks ?? []} />
      )}
    </div>
  );
}

function WorkflowCard({
  workflow,
  tasks,
  runs,
  runsLoading,
  isSelected,
  onClick,
  onLoadRuns,
}: {
  workflow: WorkflowDef;
  tasks: Task[];
  runs: WorkflowRun[];
  runsLoading: boolean;
  isSelected: boolean;
  onClick: () => void;
  onLoadRuns: () => void;
}) {
  const wfTasks = tasks.filter(t => t.workflow_id === workflow.id);
  const succeeded = wfTasks.filter(t => t.state === 'succeeded').length;
  const failed = wfTasks.filter(t => t.state === 'failed' || t.state === 'dead_letter').length;
  const totalCost = wfTasks.reduce((sum, t) => {
    const cb = t.metadata?.cost_breakdown as any;
    return sum + (cb?.total_cost_usd ?? 0);
  }, 0);

  const lastRun = runs.length > 0 ? runs[0] : null;

  return (
    <div
      className={`border rounded-xl cursor-pointer transition-all ${
        isSelected
          ? 'border-primary bg-primary/5 shadow-lg shadow-primary/10'
          : 'border-border hover:border-primary/50 hover:bg-surface-2/50'
      }`}
      onClick={onClick}
    >
      <div className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-sm truncate">{workflow.name || workflow.id}</h3>
            <p className="text-xs text-text-secondary font-mono truncate">{workflow.id}</p>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); onLoadRuns(); }}
            className="p-1.5 hover:bg-surface-3 rounded-lg transition-colors"
            title="Load runs"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-text-secondary ${runsLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs mb-3">
          <div>
            <span className="text-text-secondary">Nodes</span>
            <p className="font-medium">{workflow.nodes?.length ?? 0}</p>
          </div>
          <div>
            <span className="text-text-secondary">Tasks</span>
            <p className="font-medium">{wfTasks.length}</p>
          </div>
          <div>
            <span className="text-text-secondary">Succeeded</span>
            <p className="font-medium text-success">{succeeded}</p>
          </div>
          <div>
            <span className="text-text-secondary">Failed</span>
            <p className="font-medium text-error">{failed}</p>
          </div>
        </div>

        {totalCost > 0 && (
          <div className="flex items-center gap-1 text-xs text-success mb-2">
            <DollarSign className="w-3 h-3" />
            <span>${totalCost.toFixed(6)}</span>
          </div>
        )}

        {lastRun && (
          <div className="flex items-center justify-between text-xs text-text-secondary pt-2 border-t border-border/50">
            <span>Last run</span>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {new Date(lastRun.started_at).toLocaleString()}
            </span>
          </div>
        )}

        {runs.length > 0 && (
          <div className="mt-2 pt-2 border-t border-border/50">
            <span className="text-xs text-text-secondary">{runs.length} run(s)</span>
            <div className="flex gap-1 mt-1">
              {runs.slice(0, 8).map(r => (
                <span
                  key={r.id}
                  className={`w-2 h-2 rounded-full ${
                    r.state === 'completed' || r.state === 'succeeded' ? 'bg-success' :
                    r.state === 'failed' ? 'bg-error' :
                    r.state === 'running' ? 'bg-info animate-pulse' :
                    'bg-warning'
                  }`}
                  title={`${r.state}`}
                />
              ))}
              {runs.length > 8 && <span className="text-xs text-text-secondary">+{runs.length - 8}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const STATE_NODE_COLORS: Record<string, string> = {
  queued: '#f59e0b', running: '#3b82f6', succeeded: '#22c55e',
  failed: '#ef4444', dead_letter: '#a855f7', pending: '#f97316',
  not_started: '#6b7280',
};

function RunDagNode({ data }: { data: { label: string; state: string; agent_type: string; cost?: number; duration?: number } }) {
  const color = STATE_NODE_COLORS[data.state] ?? '#6b7280';
  return (
    <div className="rounded-xl border-2 bg-surface-2 px-4 py-3 min-w-[160px] shadow-lg" style={{ borderColor: color }}>
      <Handle type="target" position={Position.Top} className="!w-3 !h-3 !bg-border !border-2 !border-surface-3" />
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
        <span className="font-medium text-sm">{data.label}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-text-secondary">{data.agent_type}</span>
        <StatusBadge state={data.state} />
      </div>
      {data.cost != null && data.cost > 0 && (
        <div className="text-[10px] text-success mt-1">${data.cost.toFixed(6)}</div>
      )}
      {data.duration != null && data.duration > 0 && (
        <div className="text-[10px] text-text-secondary mt-0.5">{formatDuration(data.duration)}</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-border !border-2 !border-surface-3" />
    </div>
  );
}

const dagNodeTypes: NodeTypes = { runDag: RunDagNode };

function RunDagViewer({ run, wfDef, nodeDetails }: { run: WorkflowRun; wfDef: WorkflowDef; nodeDetails: { node: any; state: string; cost: number; duration: number }[] }) {
  const childMap = new Map<string, string[]>();
  wfDef.edges.forEach((e) => {
    const l = childMap.get(e.from_node_id) ?? [];
    l.push(e.to_node_id);
    childMap.set(e.from_node_id, l);
  });

  // Topological layout
  const inDeg = new Map<string, number>();
  wfDef.nodes.forEach((n) => inDeg.set(n.id, 0));
  wfDef.edges.forEach((e) => inDeg.set(e.to_node_id, (inDeg.get(e.to_node_id) ?? 0) + 1));
  const levels = new Map<string, number>();
  const queue = [...inDeg.entries()].filter(([, d]) => d === 0).map(([id]) => id);
  queue.forEach((id) => levels.set(id, 0));
  while (queue.length > 0) {
    const id = queue.shift()!;
    const lvl = levels.get(id) ?? 0;
    (childMap.get(id) ?? []).forEach((c) => {
      levels.set(c, Math.max(levels.get(c) ?? 0, lvl + 1));
      const d = (inDeg.get(c) ?? 1) - 1;
      inDeg.set(c, d);
      if (d === 0) queue.push(c);
    });
  }

  const byLevel = new Map<number, string[]>();
  levels.forEach((lvl, id) => {
    const list = byLevel.get(lvl) ?? [];
    list.push(id);
    byLevel.set(lvl, list);
  });

  const nodes: Node[] = wfDef.nodes.map((n) => {
    const lvl = levels.get(n.id) ?? 0;
    const siblings = byLevel.get(lvl) ?? [n.id];
    const idx = siblings.indexOf(n.id);
    const detail = nodeDetails.find(d => d.node.id === n.id);
    return {
      id: n.id,
      type: 'runDag',
      position: { x: 220 * idx - (siblings.length - 1) * 110, y: lvl * 150 },
      data: {
        label: n.id,
        agent_type: n.agent_type,
        state: detail?.state ?? run.node_states[n.id] ?? 'not_started',
        cost: detail?.cost ?? 0,
        duration: detail?.duration ?? 0,
      },
      draggable: false,
    };
  });

  const edges: Edge[] = wfDef.edges.map((e, i) => {
    const srcState = run.node_states[e.from_node_id] ?? '';
    const color = STATE_NODE_COLORS[srcState] ?? '#6366f1';
    return {
      id: `e-${i}`,
      source: e.from_node_id,
      target: e.to_node_id,
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color },
      style: { stroke: color, strokeWidth: 2 },
      animated: srcState === 'running',
    };
  });

  return (
    <div className="h-[450px] bg-surface rounded-lg border border-border overflow-hidden">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={dagNodeTypes} fitView nodesDraggable={false} nodesConnectable={false}>
        <Background gap={20} size={1} color="#1e2231" />
        <Controls className="!bg-surface-2 !border-border !rounded-lg [&_button]:!bg-surface-3 [&_button]:!border-border [&_button]:!text-text-secondary" />
        <MiniMap
          nodeColor={(n) => STATE_NODE_COLORS[(n.data as { state?: string })?.state ?? ''] ?? '#6b7280'}
          className="!bg-surface !border-border !rounded-lg"
        />
      </ReactFlow>
    </div>
  );
}

function TaskRow({ task }: { task: Task }) {
  const [expanded, setExpanded] = useState(false);
  const cb = task.metadata?.cost_breakdown as any;
  const duration = task.started_at && task.completed_at
    ? (new Date(task.completed_at).getTime() - new Date(task.started_at).getTime()) / 1000
    : null;

  return (
    <>
      <tr
        key={task.id}
        className="border-b border-border/50 hover:bg-surface-3/50 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="py-2 px-3 font-mono text-xs">{task.id.slice(0, 8)}</td>
        <td className="py-2 px-3 text-xs">{task.node_id ?? '—'}</td>
        <td className="py-2 px-3 text-xs">{task.agent_type}</td>
        <td className="py-2 px-3">
          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${stateBg(task.state)} ${stateColor(task.state)}`}>
            {task.state}
          </span>
        </td>
        <td className="py-2 px-3 text-right text-success text-xs">
          {cb ? `$${cb.total_cost_usd.toFixed(6)}` : '—'}
        </td>
        <td className="py-2 px-3 text-right text-xs">{cb?.total_tokens?.toLocaleString() ?? '—'}</td>
        <td className="py-2 px-3 text-right text-xs text-text-secondary">
          {duration != null ? formatDuration(duration) : '—'}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} className="p-0">
            <LazyTaskDetail task={task} />
          </td>
        </tr>
      )}
    </>
  );
}

function LazyTaskDetail({ task }: { task: Task }) {
  const [showMetadata, setShowMetadata] = useState(false);
  const cb = task.metadata?.cost_breakdown as any;

  return (
    <div className="bg-surface-3 border-b border-border px-4 py-3 text-xs space-y-3">
      {task.prompt && (
        <div>
          <span className="text-text-secondary font-medium">Prompt:</span>
          <pre className="mt-1 p-2 bg-surface-2 border border-border rounded font-mono overflow-x-auto max-h-32 whitespace-pre-wrap">
            {task.prompt}
          </pre>
        </div>
      )}
      {task.result_json && (
        <div>
          <span className="text-text-secondary font-medium">Output:</span>
          <pre className="mt-1 p-2 bg-surface-2 border border-border rounded font-mono overflow-x-auto max-h-48 whitespace-pre-wrap">
            {task.result_json}
          </pre>
        </div>
      )}
      {task.error && (
        <div>
          <span className="text-error font-medium">Error:</span>
          <pre className="mt-1 p-2 bg-error/5 border border-error/20 rounded font-mono overflow-x-auto max-h-32 text-error">
            {task.error}
          </pre>
        </div>
      )}
      {cb && (
        <div className="grid grid-cols-3 gap-3">
          <div>
            <span className="text-text-secondary">Model:</span>
            <p className="font-medium">{cb.model}</p>
          </div>
          <div>
            <span className="text-text-secondary">Prompt tokens:</span>
            <p className="font-medium">{cb.prompt_tokens?.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-text-secondary">Completion tokens:</span>
            <p className="font-medium">{cb.completion_tokens?.toLocaleString()}</p>
          </div>
          <div>
            <span className="text-text-secondary">Prompt cost:</span>
            <p className="text-success">${cb.prompt_cost_usd?.toFixed(6)}</p>
          </div>
          <div>
            <span className="text-text-secondary">Completion cost:</span>
            <p className="text-success">${cb.completion_cost_usd?.toFixed(6)}</p>
          </div>
          <div>
            <span className="text-text-secondary">Total cost:</span>
            <p className="text-success font-medium">${cb.total_cost_usd?.toFixed(6)}</p>
          </div>
        </div>
      )}
      {task.metadata && Object.keys(task.metadata).length > 0 && (
        <div>
          <button
            onClick={() => setShowMetadata(!showMetadata)}
            className="flex items-center gap-1 text-text-secondary hover:text-text-primary transition-colors"
          >
            <ChevronRight className={`w-3 h-3 transition-transform ${showMetadata ? 'rotate-90' : ''}`} />
            Metadata ({Object.keys(task.metadata).length} keys)
          </button>
          {showMetadata && (
            <pre className="mt-1 p-2 bg-surface-2 border border-border rounded font-mono overflow-x-auto max-h-48">
              {JSON.stringify(task.metadata, null, 2)}
            </pre>
          )}
        </div>
      )}
      {/* Tool executions for this task — lazy loaded */}
      <TaskToolExecutions taskId={task.id} />
    </div>
  );
}

function TaskToolExecutions({ taskId }: { taskId: string }) {
  const [execs, setExecs] = useState<ToolExecution[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (loaded) return;
    setLoading(true);
    try {
      const { fetchToolExecutions } = await import('../lib/api');
      const data = await fetchToolExecutions({ task_id: taskId, limit: 100 });
      setExecs(data);
      setLoaded(true);
    } catch {
      setExecs([]);
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  };

  if (!loaded && !loading) {
    return (
      <button
        onClick={load}
        className="flex items-center gap-1 text-text-secondary hover:text-text-primary transition-colors text-xs"
      >
        <Wrench className="w-3 h-3" />
        Load tool executions for this task
      </button>
    );
  }

  if (loading) {
    return <span className="text-xs text-text-secondary animate-pulse">Loading tool executions...</span>;
  }

  if (execs.length === 0) {
    return <span className="text-xs text-text-secondary">No tool executions for this task</span>;
  }

  return (
    <div className="space-y-1">
      <span className="text-text-secondary font-medium text-xs">Tool Executions ({execs.length}):</span>
      {execs.map(e => (
        <div key={e.id} className="flex items-center gap-2 p-2 bg-surface-2 rounded text-xs">
          {e.status === 'succeeded' ? (
            <CheckCircle2 className="w-3 h-3 text-success shrink-0" />
          ) : (
            <AlertCircle className="w-3 h-3 text-error shrink-0" />
          )}
          <span className="font-medium flex-1">{e.tool_name}</span>
          <span className="text-text-secondary">{e.duration_ms ? `${e.duration_ms.toFixed(0)}ms` : '—'}</span>
          {e.cost_usd > 0 && <span className="text-success">${e.cost_usd.toFixed(6)}</span>}
          <span className={`font-medium capitalize ${stateColor(e.status)}`}>{e.status}</span>
        </div>
      ))}
    </div>
  );
}

function RunDetail({ run, wfDef, tasks }: { run: WorkflowRun; wfDef: WorkflowDef | null; tasks: Task[] }) {
  const [toolExecs, setToolExecs] = useState<ToolExecution[]>([]);
  const [loadingTools, setLoadingTools] = useState(false);

  // Load tool executions
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoadingTools(true);
      try {
        const data = await fetchToolExecutions({ workflow_run_id: run.id, limit: 500 });
        if (!cancelled) setToolExecs(data);
      } catch {
        if (!cancelled) setToolExecs([]);
      } finally {
        if (!cancelled) setLoadingTools(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [run.id]);

  // Get tasks for this run
  const runTasks = tasks.filter(t => {
    // Match by workflow_run_id in metadata or by task_ids in run
    if (t.metadata?.workflow_run_id === run.id) return true;
    const taskIds = Object.values(run.task_ids).flat();
    return taskIds.includes(t.id);
  });

  const succeeded = runTasks.filter(t => t.state === 'succeeded').length;
  const failed = runTasks.filter(t => t.state === 'failed' || t.state === 'dead_letter').length;
  const running = runTasks.filter(t => t.state === 'running').length;
  const pending = runTasks.filter(t => t.state === 'queued' || t.state === 'pending').length;
  const total = runTasks.length;
  const totalNodes = wfDef ? wfDef.nodes.length : Object.keys(run.node_states).length;
  const completed = succeeded + failed;
  const remaining = totalNodes - completed;

  const totalCost = runTasks.reduce((sum, t) => {
    const cb = t.metadata?.cost_breakdown as any;
    return sum + (cb?.total_cost_usd ?? 0);
  }, 0);

  const totalTokens = runTasks.reduce((sum, t) => {
    const cb = t.metadata?.cost_breakdown as any;
    return sum + (cb?.total_tokens ?? 0);
  }, 0);

  // Duration
  const started = new Date(run.started_at).getTime();
  const completedTime = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  const durationSec = (completedTime - started) / 1000;

  // Cost by model
  const costByModel: Record<string, { cost: number; tokens: number; count: number }> = {};
  runTasks.forEach(t => {
    const cb = t.metadata?.cost_breakdown as any;
    if (!cb) return;
    const model = cb.model || 'unknown';
    if (!costByModel[model]) costByModel[model] = { cost: 0, tokens: 0, count: 0 };
    costByModel[model].cost += cb.total_cost_usd ?? 0;
    costByModel[model].tokens += cb.total_tokens ?? 0;
    costByModel[model].count += 1;
  });

  // Node status with task details
  const nodeDetails = (wfDef?.nodes ?? []).map(node => {
    const nodeTasks = runTasks.filter(t => t.node_id === node.id);
    const lastTask = nodeTasks[nodeTasks.length - 1];
    const state = lastTask?.state ?? run.node_states[node.id] ?? 'not_started';
    const cost = nodeTasks.reduce((sum, t) => {
      const cb = t.metadata?.cost_breakdown as any;
      return sum + (cb?.total_cost_usd ?? 0);
    }, 0);
    const duration = nodeTasks.reduce((max, t) => {
      if (t.started_at && t.completed_at) {
        const d = (new Date(t.completed_at).getTime() - new Date(t.started_at).getTime()) / 1000;
        return Math.max(max, d);
      }
      return max;
    }, 0);
    return { node, tasks: nodeTasks, state, cost, duration };
  });

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <MetricCard
          label="Tasks" value={`${succeeded}/${total}`}
          icon={<Layers className="w-5 h-5" />} color="text-success"
          sub={`${failed} failed, ${running} running, ${pending} pending`}
        />
        <MetricCard
          label="Total Cost" value={`$${totalCost.toFixed(6)}`}
          icon={<DollarSign className="w-5 h-5" />} color="text-info"
        />
        <MetricCard
          label="Total Tokens" value={totalTokens.toLocaleString()}
          icon={<Layers className="w-5 h-5" />} color="text-warning"
        />
        <MetricCard
          label="Duration" value={formatDuration(durationSec)}
          icon={<Timer className="w-5 h-5" />} color="text-primary"
        />
        <MetricCard
          label="Tool Calls" value={toolExecs.length}
          icon={<Wrench className="w-5 h-5" />} color="text-accent"
          sub={`${toolExecs.filter(e => e.status === 'failed').length} errors`}
        />
      </div>

      {/* Progress bar */}
      <Card title="Progress">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="flex justify-between text-xs text-text-secondary mb-1">
              <span>{completed} of {totalNodes} nodes completed</span>
              <span>{remaining > 0 ? `${remaining} remaining` : 'All done'}</span>
            </div>
            <div className="w-full bg-surface-3 rounded-full h-3 overflow-hidden">
              <div
                className="h-full bg-success rounded-full transition-all"
                style={{ width: `${totalNodes > 0 ? (completed / totalNodes) * 100 : 0}%` }}
              />
            </div>
          </div>
          <StatusBadge state={run.state} />
        </div>
      </Card>

      {/* DAG visualization with arrows */}
      {wfDef && wfDef.edges.length > 0 && (
        <Card title="Workflow DAG">
          <RunDagViewer run={run} wfDef={wfDef} nodeDetails={nodeDetails} />
        </Card>
      )}

      {/* Node status */}
      <Card title="Node Status">
        <div className="space-y-3">
          {nodeDetails.map(({ node, tasks: nTasks, state, cost, duration }) => (
            <div key={node.id} className="flex items-center gap-4 p-3 bg-surface-2 rounded-lg">
              <div className={`w-3 h-3 rounded-full shrink-0 ${
                state === 'succeeded' ? 'bg-success' :
                state === 'failed' || state === 'dead_letter' ? 'bg-error' :
                state === 'running' ? 'bg-info animate-pulse' :
                'bg-border'
              }`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{node.id}</span>
                  <span className="text-xs text-text-secondary">({node.agent_type})</span>
                </div>
                <p className="text-xs text-text-secondary truncate mt-0.5">{node.prompt_template}</p>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className={`font-medium capitalize ${stateColor(state)}`}>{state.replace('_', ' ')}</span>
                {cost > 0 && (
                  <span className="flex items-center gap-0.5 text-success">
                    <DollarSign className="w-3 h-3" />${cost.toFixed(6)}
                  </span>
                )}
                {duration > 0 && (
                  <span className="flex items-center gap-0.5 text-text-secondary">
                    <Timer className="w-3 h-3" />{formatDuration(duration)}
                  </span>
                )}
                {nTasks.length > 0 && (
                  <span className="text-text-secondary">{nTasks.length} task(s)</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Task list */}
      <Card title={`Tasks (${runTasks.length})`}>
        {runTasks.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-secondary text-xs uppercase tracking-wider border-b border-border">
                  <th className="text-left py-2 px-3">Task ID</th>
                  <th className="text-left py-2 px-3">Node</th>
                  <th className="text-left py-2 px-3">Agent</th>
                  <th className="text-left py-2 px-3">State</th>
                  <th className="text-right py-2 px-3">Cost</th>
                  <th className="text-right py-2 px-3">Tokens</th>
                  <th className="text-right py-2 px-3">Duration</th>
                </tr>
              </thead>
              <tbody>
                {runTasks.map(t => (
                  <TaskRow key={t.id} task={t} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon={<Layers className="w-8 h-8" />} message="No tasks for this run" />
        )}
      </Card>

      {/* Tool executions */}
      <Card title={`Tool Executions (${toolExecs.length})`}>
        {loadingTools ? (
          <LoadingState message="Loading tool executions..." />
        ) : toolExecs.length > 0 ? (
          <div className="space-y-2">
            {toolExecs.map(e => (
              <div key={e.id} className="flex items-center gap-3 p-3 bg-surface-2 rounded-lg">
                {e.status === 'succeeded' ? (
                  <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-error shrink-0" />
                )}
                <span className="text-sm font-medium flex-1">{e.tool_name}</span>
                <span className="text-xs text-text-secondary flex items-center gap-1">
                  <Timer className="w-3 h-3" />{e.duration_ms ? `${e.duration_ms.toFixed(0)}ms` : '—'}
                </span>
                {e.cost_usd > 0 && (
                  <span className="text-xs text-success">${e.cost_usd.toFixed(6)}</span>
                )}
                <span className={`text-xs font-medium capitalize ${stateColor(e.status)}`}>{e.status}</span>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Wrench className="w-8 h-8" />} message="No tool executions for this run" />
        )}
      </Card>

      {/* Cost breakdown chart */}
      {Object.keys(costByModel).length > 0 && (
        <Card title="Cost by Model">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={Object.entries(costByModel).map(([name, d]) => ({ name, ...d }))}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#8b90a0' }} axisLine={false} tickLine={false}
                tickFormatter={(v: number) => `$${v.toFixed(4)}`} />
              <Tooltip
                contentStyle={{ background: '#1e2231', border: '1px solid #2a2e3d', borderRadius: '8px', fontSize: '12px' }}
                formatter={(value: any, _name: any) => {
                  if (_name === 'cost') return [`$${Number(value).toFixed(6)}`, 'Cost'];
                  if (_name === 'tokens') return [Number(value).toLocaleString(), 'Tokens'];
                  return [value, _name];
                }}
              />
              <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
                {Object.keys(costByModel).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  );
}
