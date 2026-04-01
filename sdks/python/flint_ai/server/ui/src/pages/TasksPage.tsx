import { useState, useCallback } from 'react';
import { ListTodo, Search, RefreshCw, Send, XCircle, RotateCw, ChevronDown, ChevronRight } from 'lucide-react';
import { fetchTasks, submitTask, cancelTask, restartTask, type Task } from '../lib/api';
import { usePolling, useRelativeTime } from '../hooks/usePolling';
import { StatusBadge, Button, Card, EmptyState } from '../components/shared';

const STATES = ['all', 'queued', 'running', 'succeeded', 'failed', 'dead_letter', 'pending', 'cancelled'];

function TimeCell({ date }: { date?: string | null }) {
  return <span className="text-text-secondary">{useRelativeTime(date)}</span>;
}

function TaskRow({ task, onCancel, onRestart }: { task: Task; onCancel: (id: string) => void; onRestart: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const canCancel = ['queued', 'running'].includes(task.state);
  const canRestart = ['failed', 'dead_letter', 'cancelled'].includes(task.state);

  return (
    <>
      <tr className="border-b border-border/50 hover:bg-surface-3/30 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <td className="py-2.5 px-3">
          {expanded ? <ChevronDown className="w-3.5 h-3.5 text-text-secondary" /> : <ChevronRight className="w-3.5 h-3.5 text-text-secondary" />}
        </td>
        <td className="py-2.5 px-3 font-mono text-xs">{task.id.slice(0, 12)}</td>
        <td className="py-2.5 px-3 text-sm">{task.agent_type}</td>
        <td className="py-2.5 px-3"><StatusBadge state={task.state} /></td>
        <td className="py-2.5 px-3 text-xs">{task.attempt}/{task.max_retries}</td>
        <td className="py-2.5 px-3 max-w-[200px] truncate text-sm text-text-secondary">{task.prompt}</td>
        <td className="py-2.5 px-3 text-xs"><TimeCell date={task.created_at} /></td>
        <td className="py-2.5 px-3 text-right space-x-1">
          {canCancel && (
            <Button variant="danger" size="xs" onClick={(e) => { e.stopPropagation(); onCancel(task.id); }}>
              <XCircle className="w-3 h-3" />
            </Button>
          )}
          {canRestart && (
            <Button size="xs" onClick={(e) => { e.stopPropagation(); onRestart(task.id); }}>
              <RotateCw className="w-3 h-3" />
            </Button>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-surface-3/30">
          <td colSpan={8} className="p-4">
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <p className="text-text-secondary mb-1 uppercase tracking-wider">Prompt</p>
                <pre className="bg-surface rounded-lg p-3 overflow-auto max-h-40 whitespace-pre-wrap">{task.prompt}</pre>
              </div>
              <div>
                <p className="text-text-secondary mb-1 uppercase tracking-wider">
                  {task.error ? 'Error' : 'Result'}
                </p>
                <pre className="bg-surface rounded-lg p-3 overflow-auto max-h-40 whitespace-pre-wrap">
                  {task.error ?? task.result_json ?? '—'}
                </pre>
              </div>
              <div>
                <p className="text-text-secondary mb-1">Workflow: <span className="text-text-primary">{task.workflow_id ?? '—'}</span></p>
                <p className="text-text-secondary">Node: <span className="text-text-primary">{task.node_id ?? '—'}</span></p>
              </div>
              <div>
                <p className="text-text-secondary mb-1">Created: <span className="text-text-primary">{task.created_at}</span></p>
                <p className="text-text-secondary">Completed: <span className="text-text-primary">{task.completed_at ?? '—'}</span></p>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function TasksPage() {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [showSubmit, setShowSubmit] = useState(false);
  const [agent, setAgent] = useState('');
  const [prompt, setPrompt] = useState('');

  const params = filter !== 'all' ? `state=${filter}` : '';
  const { data: tasks, refresh } = usePolling<Task[]>(
    useCallback(() => fetchTasks(params), [params]),
    3000
  );

  const filtered = (tasks ?? []).filter((t) =>
    search ? t.id.includes(search) || t.agent_type.includes(search) || t.prompt.toLowerCase().includes(search.toLowerCase()) : true
  );

  const handleSubmit = async () => {
    if (!agent || !prompt) return;
    await submitTask({ agent_type: agent, prompt });
    setAgent(''); setPrompt(''); setShowSubmit(false);
    refresh();
  };

  const handleCancel = async (id: string) => { await cancelTask(id); refresh(); };
  const handleRestart = async (id: string) => { await restartTask(id); refresh(); };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Tasks</h1>
          <p className="text-text-secondary text-sm mt-1">{tasks?.length ?? 0} total tasks</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={refresh}><RefreshCw className="w-3.5 h-3.5" /> Refresh</Button>
          <Button variant="primary" onClick={() => setShowSubmit(!showSubmit)}>
            <Send className="w-3.5 h-3.5" /> Submit Task
          </Button>
        </div>
      </div>

      {/* Submit form */}
      {showSubmit && (
        <Card title="Submit New Task">
          <div className="flex gap-3">
            <input
              className="flex-1 bg-surface border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent"
              placeholder="Agent type (e.g. openai)"
              value={agent} onChange={(e) => setAgent(e.target.value)}
            />
            <input
              className="flex-[3] bg-surface border border-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-accent"
              placeholder="Prompt..."
              value={prompt} onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
            <Button variant="primary" size="md" onClick={handleSubmit} disabled={!agent || !prompt}>
              <Send className="w-3.5 h-3.5" /> Send
            </Button>
          </div>
        </Card>
      )}

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex gap-1 bg-surface-2 border border-border rounded-lg p-1">
          {STATES.map((s) => (
            <button
              key={s}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors capitalize ${
                filter === s ? 'bg-accent text-white' : 'text-text-secondary hover:text-text-primary'
              }`}
              onClick={() => setFilter(s)}
            >
              {s.replace('_', ' ')}
              {s !== 'all' && tasks && (
                <span className="ml-1 opacity-70">
                  ({tasks.filter((t) => t.state === s).length})
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-secondary" />
          <input
            className="w-full bg-surface-2 border border-border rounded-lg pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:border-accent"
            placeholder="Search tasks..."
            value={search} onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-surface-2 rounded-xl border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-secondary text-xs uppercase tracking-wider border-b border-border bg-surface-3/50">
                <th className="w-8 py-2.5 px-3" />
                <th className="text-left py-2.5 px-3">ID</th>
                <th className="text-left py-2.5 px-3">Agent</th>
                <th className="text-left py-2.5 px-3">State</th>
                <th className="text-left py-2.5 px-3">Retries</th>
                <th className="text-left py-2.5 px-3">Prompt</th>
                <th className="text-left py-2.5 px-3">Created</th>
                <th className="text-right py-2.5 px-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? (
                filtered.map((t) => (
                  <TaskRow key={t.id} task={t} onCancel={handleCancel} onRestart={handleRestart} />
                ))
              ) : (
                <tr>
                  <td colSpan={8}>
                    <EmptyState icon={<ListTodo className="w-8 h-8" />} message="No tasks found" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
