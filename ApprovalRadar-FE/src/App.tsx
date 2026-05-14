import { useState } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import type { ActiveTab } from '@/components/layout/DashboardLayout';
import { DashboardPage } from '@/pages/DashboardPage';
import { LogPage } from '@/pages/LogPage';
import { ToastProvider } from '@/components/ui/toast';
import { useSSE } from '@/hooks/useSSE';

export default function App() {
  useSSE(); // 앱 최상단에서 SSE 연결 및 리스닝 시작
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');

  return (
    <>
      <DashboardLayout activeTab={activeTab} onTabChange={setActiveTab}>
        {activeTab === 'dashboard' && <DashboardPage />}
        {activeTab === 'logs' && <LogPage />}
      </DashboardLayout>
      <ToastProvider />
    </>
  );
}
