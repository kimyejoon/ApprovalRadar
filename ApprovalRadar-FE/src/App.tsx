import { DashboardPage } from '@/pages/DashboardPage';
import { ToastProvider } from '@/components/ui/toast';
import { useSSE } from '@/hooks/useSSE';

export default function App() {
  useSSE(); // 앱 최상단에서 SSE 연결 및 리스닝 시작

  return (
    <>
      <DashboardPage />
      <ToastProvider />
    </>
  );
}

