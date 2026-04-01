import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  ListTodo,
  GitBranch,
  Play,
  AlertTriangle,
  Settings,
  Zap,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/tasks', icon: ListTodo, label: 'Tasks' },
  { to: '/workflows', icon: GitBranch, label: 'Workflows' },
  { to: '/runs', icon: Play, label: 'Runs' },
  { to: '/dlq', icon: AlertTriangle, label: 'Dead Letters' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Layout() {
  return (
    <div className="flex h-screen w-full">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-surface-2 border-r border-border flex flex-col">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <Zap className="w-5 h-5 text-accent" />
          <span className="font-bold text-sm tracking-tight">Flint</span>
          <span className="text-[10px] text-text-secondary bg-surface-3 px-1.5 py-0.5 rounded-full ml-auto">v1.0</span>
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
        <div className="p-3 border-t border-border text-[10px] text-text-secondary">
          Flint AI Orchestrator
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
