import { useState, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
  Handle,
  Position,
  MarkerType,
  Panel,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Plus, Save, Upload, Play, Trash2, Download, GitBranch,
} from 'lucide-react';
import {
  fetchWorkflows, fetchWorkflow, createWorkflow, updateWorkflow, deleteWorkflow,
  startWorkflow, type WorkflowDef,
} from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { Button } from '../components/shared';

/* ── Custom DAG node ── */
const AGENT_COLORS: Record<string, string> = {
  openai: '#3b82f6', claude: '#a855f7', dummy: '#22c55e',
  crewai: '#ef4444', webhook: '#f59e0b', langchain: '#06b6d4',
};

function DagNode({ data }: { data: { label: string; agent_type: string; approval?: boolean } }) {
  const color = AGENT_COLORS[data.agent_type] ?? '#6366f1';
  return (
    <div
      className="rounded-xl border-2 bg-surface-2 px-4 py-3 min-w-[160px] shadow-lg"
      style={{ borderColor: color }}
    >
      <Handle type="target" position={Position.Top} className="!w-3 !h-3 !bg-border !border-2 !border-surface-3" />
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
        <span className="font-medium text-sm">{data.label}</span>
        {data.approval && <span className="text-[10px] bg-warning/20 text-warning px-1.5 py-0.5 rounded">✋</span>}
      </div>
      <span className="text-[11px] text-text-secondary">{data.agent_type}</span>
      <Handle type="source" position={Position.Bottom} className="!w-3 !h-3 !bg-border !border-2 !border-surface-3" />
    </div>
  );
}

const nodeTypes: NodeTypes = { dag: DagNode };

/* ── Workflow → React Flow conversion ── */
function workflowToFlow(wf: WorkflowDef): { nodes: Node[]; edges: Edge[] } {
  const childMap = new Map<string, string[]>();
  wf.edges.forEach((e) => {
    const list = childMap.get(e.from_node_id) ?? [];
    list.push(e.to_node_id);
    childMap.set(e.from_node_id, list);
  });

  // Topological layout
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

  // Group by level
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
      type: 'dag',
      position: { x: 250 * idx - (siblings.length - 1) * 125, y: lvl * 140 },
      data: { label: n.id, agent_type: n.agent_type, approval: n.human_approval },
    };
  });

  const edges: Edge[] = wf.edges.map((e, i) => ({
    id: `e-${i}`,
    source: e.from_node_id,
    target: e.to_node_id,
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#6366f1' },
    style: { stroke: '#6366f1', strokeWidth: 2 },
    animated: !!e.condition,
    label: e.condition?.expression ?? (e.condition?.on_status ? e.condition.on_status.join(',') : undefined),
    labelStyle: { fill: '#8b90a0', fontSize: 10 },
    labelBgStyle: { fill: '#161922', fillOpacity: 0.9 },
  }));

  return { nodes, edges };
}

/* ── Flow → Workflow conversion ── */
function flowToWorkflow(id: string, nodes: Node[], edges: Edge[]): Partial<WorkflowDef> {
  return {
    id,
    name: id,
    nodes: nodes.map((n) => ({
      id: n.id,
      agent_type: (n.data.agent_type as string) ?? 'dummy',
      prompt_template: (n.data.prompt_template as string) ?? `Execute ${n.id}`,
      human_approval: (n.data.approval as boolean) ?? false,
    })),
    edges: edges.map((e) => ({
      from_node_id: e.source,
      to_node_id: e.target,
    })),
  };
}

/* ── Node creation modal ── */
function AddNodeModal({ onAdd, onClose }: { onAdd: (data: { id: string; agent_type: string; prompt_template: string; approval: boolean }) => void; onClose: () => void }) {
  const [id, setId] = useState(`node-${Date.now().toString(36)}`);
  const [agentType, setAgentType] = useState('openai');
  const [promptTpl, setPromptTpl] = useState('');
  const [approval, setApproval] = useState(false);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center" onClick={onClose}>
      <div className="bg-surface-2 border border-border rounded-xl p-6 w-[400px] space-y-4" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold">Add Node</h3>
        <div>
          <label className="text-xs text-text-secondary uppercase tracking-wider">Node ID</label>
          <input className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-accent"
            value={id} onChange={(e) => setId(e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-text-secondary uppercase tracking-wider">Agent Type</label>
          <select className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-accent"
            value={agentType} onChange={(e) => setAgentType(e.target.value)}>
            {Object.keys(AGENT_COLORS).map((a) => <option key={a} value={a}>{a}</option>)}
            <option value="custom">custom</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-text-secondary uppercase tracking-wider">Prompt Template</label>
          <textarea className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm mt-1 h-20 resize-none focus:outline-none focus:border-accent"
            value={promptTpl} onChange={(e) => setPromptTpl(e.target.value)} placeholder="Enter prompt for this agent..." />
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={approval} onChange={(e) => setApproval(e.target.checked)}
            className="rounded border-border" />
          Require human approval
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={() => { onAdd({ id, agent_type: agentType, prompt_template: promptTpl || `Execute ${id}`, approval }); onClose(); }}
            disabled={!id}>
            <Plus className="w-3.5 h-3.5" /> Add Node
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ── Main editor page ── */
export default function WorkflowsPage() {
  const { data: workflows, refresh } = usePolling<WorkflowDef[]>(
    useCallback(() => fetchWorkflows(), []),
    5000
  );

  const [activeWf, setActiveWf] = useState<string | null>(null);
  const [wfId, setWfId] = useState('new-workflow');
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [showAddNode, setShowAddNode] = useState(false);
  const [saving, setSaving] = useState(false);

  const onConnect = useCallback(
    (conn: Connection) =>
      setEdges((eds) =>
        addEdge({
          ...conn,
          markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#6366f1' },
        }, eds)
      ),
    [setEdges]
  );

  const loadWorkflow = async (id: string) => {
    const wf = await fetchWorkflow(id);
    const { nodes: n, edges: e } = workflowToFlow(wf);
    setNodes(n);
    setEdges(e);
    setWfId(wf.id);
    setActiveWf(wf.id);
  };

  const handleAddNode = (data: { id: string; agent_type: string; prompt_template: string; approval: boolean }) => {
    const newNode: Node = {
      id: data.id,
      type: 'dag',
      position: { x: Math.random() * 400, y: Math.random() * 300 + 50 },
      data: { label: data.id, agent_type: data.agent_type, prompt_template: data.prompt_template, approval: data.approval },
    };
    setNodes((nds) => [...nds, newNode]);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const wf = flowToWorkflow(wfId, nodes, edges);
      if (activeWf) {
        await updateWorkflow(activeWf, wf);
      } else {
        await createWorkflow(wf);
        setActiveWf(wfId);
      }
      refresh();
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    if (!activeWf) return;
    await startWorkflow(activeWf);
  };

  const handleDelete = async () => {
    if (!activeWf) return;
    await deleteWorkflow(activeWf);
    setActiveWf(null);
    setNodes([]);
    setEdges([]);
    setWfId('new-workflow');
    refresh();
  };

  const handleExportJson = () => {
    const wf = flowToWorkflow(wfId, nodes, edges);
    navigator.clipboard.writeText(JSON.stringify(wf, null, 2));
  };

  const handleImportJson = () => {
    const json = prompt('Paste workflow JSON:');
    if (!json) return;
    try {
      const wf = JSON.parse(json) as WorkflowDef;
      const { nodes: n, edges: e } = workflowToFlow(wf);
      setNodes(n);
      setEdges(e);
      setWfId(wf.id);
    } catch {
      alert('Invalid JSON');
    }
  };

  const handleDeleteSelected = () => {
    setNodes((nds) => nds.filter((n) => !n.selected));
    setEdges((eds) => eds.filter((e) => !e.selected));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Workflow Editor</h1>
          <p className="text-text-secondary text-sm mt-1">Visual DAG builder</p>
        </div>
      </div>

      <div className="grid grid-cols-[240px_1fr] gap-4 h-[calc(100vh-180px)]">
        {/* Sidebar: workflow list */}
        <div className="bg-surface-2 rounded-xl border border-border overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="text-sm font-medium">Workflows</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            <button
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                !activeWf ? 'bg-accent/10 text-accent' : 'text-text-secondary hover:bg-surface-3'
              }`}
              onClick={() => { setActiveWf(null); setNodes([]); setEdges([]); setWfId('new-workflow'); }}
            >
              <Plus className="w-3.5 h-3.5 inline mr-1.5" /> New Workflow
            </button>
            {(workflows ?? []).map((wf) => (
              <button
                key={wf.id}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  activeWf === wf.id ? 'bg-accent/10 text-accent' : 'text-text-secondary hover:bg-surface-3'
                }`}
                onClick={() => loadWorkflow(wf.id)}
              >
                <GitBranch className="w-3.5 h-3.5 inline mr-1.5" />
                {wf.name ?? wf.id}
                <span className="block text-[10px] opacity-60">{wf.nodes.length} nodes, {wf.edges.length} edges</span>
              </button>
            ))}
            {(!workflows || workflows.length === 0) && (
              <p className="text-xs text-text-secondary text-center py-4">No workflows yet</p>
            )}
          </div>
        </div>

        {/* Canvas */}
        <div className="bg-surface-2 rounded-xl border border-border overflow-hidden relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
            snapToGrid
            snapGrid={[20, 20]}
            deleteKeyCode={['Backspace', 'Delete']}
            defaultEdgeOptions={{
              markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: '#6366f1' },
              style: { stroke: '#6366f1', strokeWidth: 2 },
            }}
          >
            <Background gap={20} size={1} color="#1e2231" />
            <Controls className="!bg-surface-2 !border-border !rounded-lg [&_button]:!bg-surface-3 [&_button]:!border-border [&_button]:!text-text-secondary" />
            <MiniMap
              nodeColor={(n) => AGENT_COLORS[(n.data as { agent_type?: string })?.agent_type ?? ''] ?? '#6366f1'}
              className="!bg-surface !border-border !rounded-lg"
            />
            <Panel position="top-left" className="flex gap-2">
              <div className="bg-surface-2 border border-border rounded-lg px-3 py-1.5 flex items-center gap-2">
                <label className="text-xs text-text-secondary">ID:</label>
                <input
                  className="bg-transparent text-sm font-medium w-40 focus:outline-none"
                  value={wfId} onChange={(e) => setWfId(e.target.value)}
                />
              </div>
            </Panel>
            <Panel position="top-right" className="flex gap-2">
              <Button onClick={() => setShowAddNode(true)}><Plus className="w-3.5 h-3.5" /> Add Node</Button>
              <Button onClick={handleDeleteSelected} variant="danger"><Trash2 className="w-3.5 h-3.5" /></Button>
              <Button onClick={handleImportJson}><Upload className="w-3.5 h-3.5" /> Import</Button>
              <Button onClick={handleExportJson}><Download className="w-3.5 h-3.5" /> Export</Button>
              <Button onClick={handleSave} variant="primary" disabled={saving}>
                <Save className="w-3.5 h-3.5" /> {saving ? 'Saving...' : 'Save'}
              </Button>
              {activeWf && (
                <>
                  <Button onClick={handleRun} variant="primary"><Play className="w-3.5 h-3.5" /> Run</Button>
                  <Button onClick={handleDelete} variant="danger"><Trash2 className="w-3.5 h-3.5" /> Delete</Button>
                </>
              )}
            </Panel>
          </ReactFlow>
        </div>
      </div>

      {showAddNode && <AddNodeModal onAdd={handleAddNode} onClose={() => setShowAddNode(false)} />}
    </div>
  );
}
