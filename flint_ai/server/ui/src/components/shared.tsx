import { type ReactNode, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

// Status badge
const stateColors: Record<string, string> = {
  queued: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  running: 'bg-blue-500/20 text-blue-400 border-blue-500/30 animate-pulse-ring',
  succeeded: 'bg-green-500/20 text-green-400 border-green-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  dead_letter: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
  pending: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  cancelled: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
};

export function StatusBadge({ state }: { state: string }) {
  const cls = stateColors[state] ?? 'bg-gray-500/20 text-gray-400';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {state.replace('_', ' ')}
    </span>
  );
}

// Spinner
export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' };
  return <Loader2 className={`${sizes[size]} animate-spin text-accent`} />;
}

// Full-page loading state
export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-text-secondary">
      <Spinner size="lg" />
      <p className="text-sm mt-3">{message}</p>
    </div>
  );
}

// Inline error alert
export function ErrorAlert({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-lg border border-red-500/30 bg-red-500/10">
      <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
      <p className="text-sm text-red-400 flex-1">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-xs font-medium text-red-400 hover:text-red-300 underline underline-offset-2"
        >
          Retry
        </button>
      )}
    </div>
  );
}

// Metric card
export function MetricCard({
  label,
  value,
  icon,
  color = 'text-accent',
  sub,
  trend,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
  color?: string;
  sub?: string;
  trend?: 'up' | 'down' | 'neutral';
}) {
  const trendColors = { up: 'text-success', down: 'text-error', neutral: 'text-text-secondary' };
  return (
    <div className="bg-surface-2 rounded-xl border border-border p-4 flex items-start gap-3 hover:border-border-hover transition-colors">
      <div className={`p-2 rounded-lg bg-surface-3 ${color}`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-text-secondary text-xs uppercase tracking-wider">{label}</p>
        <p className="text-2xl font-semibold mt-0.5">
          {value}
          {trend && <span className={`text-xs ml-1.5 ${trendColors[trend]}`}>
            {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
          </span>}
        </p>
        {sub && <p className="text-text-secondary text-xs mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// Card wrapper
export function Card({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="bg-surface-2 rounded-xl border border-border overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-border">
        <h3 className="font-medium text-sm">{title}</h3>
        {actions}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

// Button variants
export function Button({
  children,
  variant = 'default',
  size = 'sm',
  loading = false,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  size?: 'xs' | 'sm' | 'md';
  loading?: boolean;
}) {
  const base = 'inline-flex items-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  const sizes = { xs: 'px-2 py-0.5 text-xs', sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2 text-sm' };
  const variants = {
    default: 'bg-surface-3 text-text-primary border border-border hover:border-border-hover',
    primary: 'bg-accent text-white hover:bg-accent-hover',
    danger: 'bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20',
    ghost: 'text-text-secondary hover:text-text-primary hover:bg-surface-3',
  };
  return (
    <button className={`${base} ${sizes[size]} ${variants[variant]}`} disabled={loading || props.disabled} {...props}>
      {loading ? <Spinner size="sm" /> : children}
    </button>
  );
}

// Progress bar
export function ProgressBar({ value, max, color = 'bg-accent' }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const barColor = pct > 80 ? 'bg-error' : pct > 50 ? 'bg-warning' : color;
  return (
    <div className="w-full h-2 bg-surface-3 rounded-full overflow-hidden">
      <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

// Empty state
export function EmptyState({ icon, message, action }: { icon: ReactNode; message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-text-secondary">
      <div className="mb-3 opacity-40">{icon}</div>
      <p className="text-sm">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// Confirm dialog
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  variant = 'danger',
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  variant?: 'danger' | 'primary';
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center" onClick={onCancel}>
      <div className="bg-surface-2 border border-border rounded-xl p-6 w-[400px]" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-2">{title}</h3>
        <p className="text-sm text-text-secondary mb-6">{message}</p>
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel}>Cancel</Button>
          <Button variant={variant} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}

// Pagination
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-border">
      <span className="text-xs text-text-secondary">
        Showing {Math.min((page - 1) * pageSize + 1, total)}–{Math.min(page * pageSize, total)} of {total}
      </span>
      <div className="flex gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className="px-2 py-1 text-xs rounded border border-border text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
        >
          ← Prev
        </button>
        {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
          let pageNum: number;
          if (totalPages <= 7) {
            pageNum = i + 1;
          } else if (page <= 4) {
            pageNum = i + 1;
          } else if (page >= totalPages - 3) {
            pageNum = totalPages - 6 + i;
          } else {
            pageNum = page - 3 + i;
          }
          return (
            <button
              key={pageNum}
              onClick={() => onPageChange(pageNum)}
              className={`px-2.5 py-1 text-xs rounded border transition-colors ${
                pageNum === page
                  ? 'bg-accent text-white border-accent'
                  : 'border-border text-text-secondary hover:text-text-primary'
              }`}
            >
              {pageNum}
            </button>
          );
        })}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className="px-2 py-1 text-xs rounded border border-border text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Next →
        </button>
      </div>
    </div>
  );
}

// Skeleton loader
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`bg-surface-3 animate-pulse rounded ${className}`} />;
}

// Copy to clipboard button
export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={handleCopy} className="text-xs text-text-secondary hover:text-accent transition-colors">
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}
