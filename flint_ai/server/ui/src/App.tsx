import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import DashboardPage from './pages/DashboardPage';
import TasksPage from './pages/TasksPage';
import WorkflowsPage from './pages/WorkflowsPage';
import RunsPage from './pages/RunsPage';
import DLQPage from './pages/DLQPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <BrowserRouter basename="/ui">
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
              <Route path="tasks" element={<ErrorBoundary><TasksPage /></ErrorBoundary>} />
              <Route path="workflows" element={<ErrorBoundary><WorkflowsPage /></ErrorBoundary>} />
              <Route path="runs" element={<ErrorBoundary><RunsPage /></ErrorBoundary>} />
              <Route path="dlq" element={<ErrorBoundary><DLQPage /></ErrorBoundary>} />
              <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  );
}
