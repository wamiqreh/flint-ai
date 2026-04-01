import { useState, useCallback } from 'react';
import { AlertTriangle, RotateCw, Trash2, Search, Eye, X } from 'lucide-react';
import { fetchDLQ, retryDLQ, purgeDLQ, type DLQMessage } from '../lib/api';
import { usePolling } from '../hooks/usePolling';
import { Button, EmptyState } from '../components/shared';
export default function DLQPage() {
  const { data: messages, refresh } = usePolling<DLQMessage[]>(
    useCallback(() => fetchDLQ(), []),
    5000
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<DLQMessage | null>(null);
  const [search, setSearch] = useState('');

  const filtered = (messages ?? []).filter((m) =>
    search
      ? m.task_id.includes(search) ||
        JSON.stringify(m.data).toLowerCase().includes(search.toLowerCase())
      : true
  );

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === filtered.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map((m) => m.message_id)));
    }
  };

  const handleRetry = async (id: string) => {
    await retryDLQ(id);
    refresh();
  };

  const handleRetrySelected = async () => {
    await Promise.all([...selected].map((id) => retryDLQ(id)));
    setSelected(new Set());
    refresh();
  };

  const handlePurge = async () => {
    if (!confirm('Purge all dead letter messages? This cannot be undone.')) return;
    await purgeDLQ();
    setSelected(new Set());
    refresh();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dead Letter Queue</h1>
          <p className="text-text-secondary text-sm mt-1">
            {messages?.length ?? 0} messages in DLQ
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <Button onClick={handleRetrySelected}>
              <RotateCw className="w-3.5 h-3.5" /> Retry Selected ({selected.size})
            </Button>
          )}
          <Button variant="danger" onClick={handlePurge} disabled={!messages?.length}>
            <Trash2 className="w-3.5 h-3.5" /> Purge All
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-secondary" />
        <input
          className="w-full bg-surface-2 border border-border rounded-lg pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:border-accent"
          placeholder="Search DLQ..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Table */}
      <div className="bg-surface-2 rounded-xl border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-secondary text-xs uppercase tracking-wider border-b border-border bg-surface-3/50">
                <th className="w-10 py-2.5 px-3">
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selected.size === filtered.length}
                    onChange={toggleAll}
                    className="rounded border-border"
                  />
                </th>
                <th className="text-left py-2.5 px-3">Message ID</th>
                <th className="text-left py-2.5 px-3">Task ID</th>
                <th className="text-left py-2.5 px-3">Agent</th>
                <th className="text-left py-2.5 px-3">Error</th>
                <th className="text-right py-2.5 px-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length > 0 ? (
                filtered.map((msg) => (
                  <tr key={msg.message_id} className="border-b border-border/50 hover:bg-surface-3/30">
                    <td className="py-2.5 px-3">
                      <input
                        type="checkbox"
                        checked={selected.has(msg.message_id)}
                        onChange={() => toggleSelect(msg.message_id)}
                        className="rounded border-border"
                      />
                    </td>
                    <td className="py-2.5 px-3 font-mono text-xs">{msg.message_id.slice(0, 12)}</td>
                    <td className="py-2.5 px-3 font-mono text-xs">{msg.task_id.slice(0, 12)}</td>
                    <td className="py-2.5 px-3">{(msg.data.agent_type as string) ?? '—'}</td>
                    <td className="py-2.5 px-3 max-w-xs truncate text-error text-xs">
                      {(msg.data.dlq_reason as string) ?? '—'}
                    </td>
                    <td className="py-2.5 px-3 text-right space-x-1">
                      <Button size="xs" onClick={() => setDetail(msg)}>
                        <Eye className="w-3 h-3" />
                      </Button>
                      <Button size="xs" onClick={() => handleRetry(msg.message_id)}>
                        <RotateCw className="w-3 h-3" />
                      </Button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={<AlertTriangle className="w-8 h-8" />}
                      message="No dead letter messages"
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail modal */}
      {detail && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center" onClick={() => setDetail(null)}>
          <div className="bg-surface-2 border border-border rounded-xl p-6 w-[600px] max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">DLQ Message Detail</h3>
              <button onClick={() => setDetail(null)} className="text-text-secondary hover:text-text-primary">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-text-secondary text-xs uppercase tracking-wider">Message ID</span>
                <p className="font-mono text-xs mt-0.5">{detail.message_id}</p>
              </div>
              <div>
                <span className="text-text-secondary text-xs uppercase tracking-wider">Task ID</span>
                <p className="font-mono text-xs mt-0.5">{detail.task_id}</p>
              </div>
              <div>
                <span className="text-text-secondary text-xs uppercase tracking-wider">Full Data</span>
                <pre className="bg-surface rounded-lg p-3 mt-1 overflow-auto max-h-60 text-xs whitespace-pre-wrap">
                  {JSON.stringify(detail.data, null, 2)}
                </pre>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-border">
              <Button onClick={() => setDetail(null)}>Close</Button>
              <Button variant="primary" onClick={() => { handleRetry(detail.message_id); setDetail(null); }}>
                <RotateCw className="w-3.5 h-3.5" /> Retry
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
