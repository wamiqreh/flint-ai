import { NavLink, Outlet } from 'react-router-dom';
import { useCallback } from 'react';
import {
  LayoutDashboard,
  ListTodo,
  GitBranch,
  Play,
  AlertTriangle,
  Settings,
  Zap,
  Wifi,
  WifiOff,
  DollarSign,
  Wrench,
} from 'lucide-react';
import { fetchHealth, type HealthStatus } from '../lib/api';
import { usePolling } from '../hooks/usePolling';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/tasks', icon: ListTodo, label: 'Tasks' },
  { to: '/workflows', icon: GitBranch, label: 'Workflows' },
  { to: '/runs', icon: Play, label: 'Runs' },
  { to: '/costs', icon: DollarSign, label: 'Costs' },
  { to: '/tools', icon: Wrench, label: 'Tools' },
  { to: '/dlq', icon: AlertTriangle, label: 'Dead Letters' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Layout() {
  const { data: health, error: healthError } = usePolling<HealthStatus>(
    useCallback(() => fetchHealth(), []),
    10000
  );
  const isConnected = health && !healthError;
  const isHealthy = health?.status === 'healthy';

  return (
    <div className="flex h-screen w-full">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-surface-2 border-r border-border flex flex-col">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <Zap className="w-5 h-5 text-accent" />
          <span className="font-bold text-sm tracking-tight">Flint</span>
          <span className="text-[10px] text-text-secondary bg-surface-3 px-1.5 py-0.5 rounded-full ml-auto">AI</span>
        </div>
        <nav className="flex-1 py-2 px-2 space-y-0.5">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-accent/10 text-accent font-medium'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-3'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-border">
          <div className="flex items-center gap-2 text-[10px] text-text-secondary">
            {isConnected ? (
              <>
                <Wifi className={`w-3 h-3 ${isHealthy ? 'text-success' : 'text-warning'}`} />
                <span>{isHealthy ? 'Connected' : 'Degraded'}</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3 h-3 text-error" />
                <span>Disconnected</span>
              </>
            )}
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-6 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
