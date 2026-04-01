import { useState, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
  Handle,
  Position,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Play, Eye, Clock, CheckCircle2, XCircle } from 'lucide-react';
import {
  fetchWorkflows, fetchWorkflowRuns, fetchWorkflow,
  type WorkflowDef, type WorkflowRun,
} from '../lib/api';
import { usePolling, useRelativeTime } from '../hooks/usePolling';
import { StatusBadge, Card, EmptyState } from '../components/shared';

const STATE_NODE_COLORS: Record<string, string> = {
  queued: '#f59e0b', running: '#3b82f6', succeeded: '#22c55e',
  failed: '#ef4444', dead_letter: '#a855f7', pending: '#f97316',
};

function RunDagNode({ data }: { data: { label: string; state: string; agent_type: string } }) {
  const color = STATE_NODE_COLORS[data.state] ?? '#6b7280';
  const isRunning = data.state === 'running';
  return (
    <div className={`rounded-xl border-2 bg-surface-2 px-4 py-3 min-w-[140px] ${isRunning ? 'animate-pulse-ring' : ''}`}
      style={{ borderColor: color }}>
      <Handle type="target" position={Position.Top} className="!w-3 !h-3 !bg-border !border-2 !border-surface-3" />
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
        <span className="font-medium text-sm">{data.label}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-text-secondary">{data.agent_type}</span>
        <StatusBadge state={data.state} />
      </div>
      <Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-border !border-2 !border-surface-3" />
    </div>
  );
}

const nodeTypes: NodeTypes = { runDag: RunDagNode };

function RunViewer({ run, wf }: { run: WorkflowRun; wf: WorkflowDef }) {
  const childMap = new Map<string, string[]>();
  wf.edges.forEach((e) => {
    const l = childMap.get(e.from_node_id) ?? [];
    l.push(e.to_node_id);
    childMap.set(e.from_node_id, l);
  });

  // Layout
  const inDeg = new Map<string, number>();
  wf.nodes.forEach((n) => inDeg.set(n.id, 0));
  wf.edges.forEach((e) => inDeg.set(e.to_node_id, (inDeg.get(e.to_node_id) ?? 0) + 1));
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

  const nodes: Node[] = wf.nodes.map((n) => {
    const lvl = levels.get(n.id) ?? 0;
    const siblings = byLevel.get(lvl) ?? [n.id];
    const idx = siblings.indexOf(n.id);
    return {
      id: n.id,
      type: 'runDag',
      position: { x: 220 * idx - (siblings.length - 1) * 110, y: lvl * 130 },
      data: {
        label: n.id,
        agent_type: n.agent_type,
        state: run.node_states[n.id] ?? 'queued',
      },
      draggable: false,
    };
  });

  const edges: Edge[] = wf.edges.map((e, i) => {
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
    <div className="h-[400px] bg-surface rounded-lg border border-border overflow-hidden">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView nodesDraggable={false} nodesConnectable={false}>
        <Background gap={20} size={1} color="#1e2231" />
        <Controls className="!bg-surface-2 !border-border !rounded-lg [&_button]:!bg-surface-3 [&_button]:!border-border [&_button]:!text-text-secondary" />
      </ReactFlow>
    </div>
  );
}

function TimeAgo({ date }: { date?: string | null }) {
  return <span>{useRelativeTime(date)}</span>;
}

const RUN_STATE_ICONS: Record<string, React.ReactNode> = {
  running: <Play className="w-3.5 h-3.5 text-blue-400" />,
  completed: <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-400" />,
};

export default function RunsPage() {
  const { data: workflows } = usePolling<WorkflowDef[]>(
    useCallback(() => fetchWorkflows(), []),
    10000
  );
  const [selectedWf, setSelectedWf] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [wfDef, setWfDef] = useState<WorkflowDef | null>(null);

  const { data: runs } = usePolling<WorkflowRun[]>(
    useCallback(() => selectedWf ? fetchWorkflowRuns(selectedWf) : Promise.resolve([]), [selectedWf]),
    3000,
    !!selectedWf
  );

  const handleSelectRun = async (run: WorkflowRun) => {
    setSelectedRun(run);
    if (!wfDef || wfDef.id !== run.workflow_id) {
      const wf = await fetchWorkflow(run.workflow_id);
      setWfDef(wf);
    }
  };

  const totalNodes = (run: WorkflowRun) => Object.keys(run.node_states).length;
  const completedNodes = (run: WorkflowRun) =>
    Object.values(run.node_states).filter((s) => ['succeeded', 'failed', 'dead_letter'].includes(s)).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Workflow Runs</h1>
        <p className="text-text-secondary text-sm mt-1">Monitor workflow execution in real-time</p>
      </div>

      {/* Workflow selector */}
      <div className="flex items-center gap-3">
        <select
          className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent"
          value={selectedWf ?? ''}
          onChange={(e) => { setSelectedWf(e.target.value || null); setSelectedRun(null); }}
        >
          <option value="">Select a workflow...</option>
          {(workflows ?? []).map((wf) => (
            <option key={wf.id} value={wf.id}>{wf.name ?? wf.id}</option>
          ))}
        </select>
      </div>

      {!selectedWf ? (
        <EmptyState icon={<Play className="w-8 h-8" />} message="Select a workflow to view its runs" />
      ) : (
        <div className="grid grid-cols-[300px_1fr] gap-4">
          {/* Runs list */}
          <div className="bg-surface-2 rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h3 className="text-sm font-medium">Runs ({runs?.length ?? 0})</h3>
            </div>
            <div className="overflow-y-auto max-h-[600px] p-2 space-y-1">
              {(runs ?? []).map((run) => (
                <button
                  key={run.id}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
                    selectedRun?.id === run.id ? 'bg-accent/10 border border-accent/30' : 'hover:bg-surface-3 border border-transparent'
                  }`}
                  onClick={() => handleSelectRun(run)}
                >
                  <div className="flex items-center gap-2">
                    {RUN_STATE_ICONS[run.state] ?? <Clock className="w-3.5 h-3.5 text-text-secondary" />}
                    <span className="font-mono text-xs">{run.id.slice(0, 8)}</span>
                    <StatusBadge state={run.state} />
                  </div>
                  <div className="mt-1 text-[10px] text-text-secondary flex justify-between">
                    <span>{completedNodes(run)}/{totalNodes(run)} nodes</span>
                    <TimeAgo date={run.started_at} />
                  </div>
                </button>
              ))}
              {(!runs || runs.length === 0) && (
                <p className="text-xs text-text-secondary text-center py-4">No runs yet</p>
              )}
            </div>
          </div>

          {/* DAG visualization */}
          <div className="space-y-4">
            {selectedRun && wfDef ? (
              <>
                <Card title={`Run ${selectedRun.id.slice(0, 12)}`}
                  actions={<StatusBadge state={selectedRun.state} />}>
                  <div className="grid grid-cols-3 gap-4 text-sm mb-4">
                    <div>
                      <span className="text-text-secondary text-xs">Started</span>
                      <p>{selectedRun.started_at}</p>
                    </div>
                    <div>
                      <span className="text-text-secondary text-xs">Completed</span>
                      <p>{selectedRun.completed_at ?? '—'}</p>
                    </div>
                    <div>
                      <span className="text-text-secondary text-xs">Progress</span>
                      <p>{completedNodes(selectedRun)}/{totalNodes(selectedRun)} nodes</p>
                    </div>
                  </div>
                  <RunViewer run={selectedRun} wf={wfDef} />
                </Card>

                {/* Node states table */}
                <Card title="Node States">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-text-secondary text-xs uppercase tracking-wider border-b border-border">
                        <th className="text-left py-2 px-3">Node</th>
                        <th className="text-left py-2 px-3">State</th>
                        <th className="text-left py-2 px-3">Task ID</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(selectedRun.node_states).map(([node, state]) => (
                        <tr key={node} className="border-b border-border/50">
                          <td className="py-2 px-3 font-medium">{node}</td>
                          <td className="py-2 px-3"><StatusBadge state={state} /></td>
                          <td className="py-2 px-3 font-mono text-xs text-text-secondary">
                            {selectedRun.task_ids[node]?.slice(0, 12) ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              </>
            ) : (
              <EmptyState icon={<Eye className="w-8 h-8" />} message="Select a run to view its DAG" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
