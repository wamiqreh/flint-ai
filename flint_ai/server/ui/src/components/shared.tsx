import type { ReactNode } from 'react';

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

// Metric card
export function MetricCard({
  label,
  value,
  icon,
  color = 'text-accent',
  sub,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
  color?: string;
  sub?: string;
}) {
  return (
    <div className="bg-surface-2 rounded-xl border border-border p-4 flex items-start gap-3 hover:border-border-hover transition-colors">
      <div className={`p-2 rounded-lg bg-surface-3 ${color}`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-text-secondary text-xs uppercase tracking-wider">{label}</p>
        <p className="text-2xl font-semibold mt-0.5">{value}</p>
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
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'primary' | 'danger' | 'ghost';
  size?: 'xs' | 'sm' | 'md';
}) {
  const base = 'inline-flex items-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50';
  const sizes = { xs: 'px-2 py-0.5 text-xs', sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2 text-sm' };
  const variants = {
    default: 'bg-surface-3 text-text-primary border border-border hover:border-border-hover',
    primary: 'bg-accent text-white hover:bg-accent-hover',
    danger: 'bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20',
    ghost: 'text-text-secondary hover:text-text-primary hover:bg-surface-3',
  };
  return (
    <button className={`${base} ${sizes[size]} ${variants[variant]}`} {...props}>
      {children}
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
export function EmptyState({ icon, message }: { icon: ReactNode; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-text-secondary">
      <div className="mb-3 opacity-40">{icon}</div>
      <p className="text-sm">{message}</p>
    </div>
  );
}
