import { useEffect, useState } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import type { ActiveTab } from '@/components/layout/DashboardLayout';
import { DashboardPage } from '@/pages/DashboardPage';
import { LogPage } from '@/pages/LogPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { PlaygroundPage } from '@/pages/PlaygroundPage';
import { ToastProvider } from '@/components/ui/toast';
import { useSSE } from '@/hooks/useSSE';
import { SystemAlertPopup } from '@/components/ui/SystemAlertPopup';
import { emitSystemAlert } from '@/lib/systemAlertEmitter';

// 전역 개발자 도구 타입 선언
declare global {
  interface Window {
    __radar__?: {
      testWarn: (msg?: string) => void;
      testAlert: (msg?: string) => void;
      testUpdate: () => void;
    };
  }
}

export default function App() {
  useSSE(); // 앱 최상단에서 SSE 연결 및 리스닝 시작
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');

  // DEV 환경 전용 window.__radar__ 개발자 콘솔 도구 등록
  useEffect(() => {
    if (import.meta.env.DEV && typeof window !== 'undefined') {
      window.__radar__ = {
        testWarn: (msg = 'API 키 잔여량 경고: test***key 키가 950/1000건 사용됨 — 잔여 50건') => {
          emitSystemAlert('WARN', msg);
        },
        testAlert: (msg = '크롤러 연속 3회 실패: 식품업소 인허가변경 크롤러가 3회 연속 오류를 발생했습니다.') => {
          emitSystemAlert('ALERT', msg);
        },
        testUpdate: () => {
          // 기존 triggerTestNotification 위임
          if (window.triggerTestNotification) window.triggerTestNotification();
        },
      };
      console.info(
        '%c[ApprovalRadar DevTools]%c window.__radar__ 등록됨\n' +
        '  window.__radar__.testWarn()   — WARN 팝업 테스트\n' +
        '  window.__radar__.testAlert()  — ALERT 팝업 테스트\n' +
        '  window.__radar__.testUpdate() — SSE UPDATE 테스트',
        'color: #4ade80; font-weight: bold;',
        'color: inherit;'
      );
    }
    return () => {
      if (import.meta.env.DEV && typeof window !== 'undefined') {
        delete window.__radar__;
      }
    };
  }, []);

  return (
    <>
      <DashboardLayout activeTab={activeTab} onTabChange={setActiveTab}>
        {activeTab === 'dashboard' && <DashboardPage />}
        {activeTab === 'logs' && <LogPage />}
        {activeTab === 'settings' && <SettingsPage />}
        {activeTab === 'playground' && <PlaygroundPage />}
      </DashboardLayout>
      <ToastProvider />
      <SystemAlertPopup />
    </>
  );
}
