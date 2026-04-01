import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import DashboardPage from './pages/DashboardPage';
import TasksPage from './pages/TasksPage';
import WorkflowsPage from './pages/WorkflowsPage';
import RunsPage from './pages/RunsPage';
import DLQPage from './pages/DLQPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  return (
    <BrowserRouter basename="/ui">
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="workflows" element={<WorkflowsPage />} />
          <Route path="runs" element={<RunsPage />} />
          <Route path="dlq" element={<DLQPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
