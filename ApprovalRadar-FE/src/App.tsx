import { useEffect, useState, useRef } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import type { ActiveTab } from '@/components/layout/DashboardLayout';
import { DashboardPage } from '@/pages/DashboardPage';
import { NewMonitorPage } from '@/pages/NewMonitorPage';
import { LogPage } from '@/pages/LogPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { PlaygroundPage } from '@/pages/PlaygroundPage';
import { ToastProvider } from '@/components/ui/toast';
import { useSSE } from '@/hooks/useSSE';
import { useNotification } from '@/hooks/useNotification';
import { SystemAlertPopup } from '@/components/ui/SystemAlertPopup';
import { emitSystemAlert } from '@/lib/systemAlertEmitter';

const HASH_TO_TAB: Record<string, ActiveTab> = {
  '#/change-monitor': 'change-monitor',
  '#/new-monitor': 'new-monitor',
  '#/logs': 'logs',
  '#/settings': 'settings',
  '#/playground': 'playground',
};

const TAB_TO_HASH: Record<ActiveTab, string> = {
  'change-monitor': '#/change-monitor',
  'new-monitor': '#/new-monitor',
  'logs': '#/logs',
  'settings': '#/settings',
  'playground': '#/playground',
};

function getTabFromHash(hash: string): ActiveTab {
  const cleanHash = hash.split('?')[0] || '';
  if (cleanHash === '#/dashboard' || cleanHash === '#' || cleanHash === '') {
    return 'change-monitor';
  }
  return HASH_TO_TAB[cleanHash] || 'change-monitor';
}

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
  const { sendNotification } = useNotification(); // 최초 마운트 시 알림 권한 요청
  useSSE(sendNotification); // SSE 연결 + 백그라운드 탭 알림 연동

  const lastTabHashes = useRef<Record<ActiveTab, string>>({
    'change-monitor': '#/change-monitor',
    'new-monitor': '#/new-monitor',
    'logs': '#/logs',
    'settings': '#/settings',
    'playground': '#/playground',
  });

  const [activeTab, setActiveTab] = useState<ActiveTab>(() => {
    if (typeof window !== 'undefined') {
      const tab = getTabFromHash(window.location.hash);
      return tab;
    }
    return 'change-monitor';
  });

  useEffect(() => {
    // Initialize the ref with the initial hash if it matches activeTab
    if (typeof window !== 'undefined' && window.location.hash) {
      const tab = getTabFromHash(window.location.hash);
      lastTabHashes.current[tab] = window.location.hash;
    }
  }, []);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash;
      const tab = getTabFromHash(hash);
      setActiveTab(tab);
      if (hash) {
        lastTabHashes.current[tab] = hash;
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    
    // Redirect empty/invalid/old dashboard hash to change-monitor
    const currentCleanHash = window.location.hash.split('?')[0];
    if (!currentCleanHash || currentCleanHash === '#/dashboard') {
      window.location.hash = '#/change-monitor';
    } else {
      // Capture initial hash state in ref
      const tab = getTabFromHash(window.location.hash);
      lastTabHashes.current[tab] = window.location.hash;
    }

    return () => {
      window.removeEventListener('hashchange', handleHashChange);
    };
  }, []);

  const handleTabChange = (tab: ActiveTab) => {
    if (typeof window !== 'undefined') {
      // Before switching, capture current URL hash for the current active tab
      lastTabHashes.current[activeTab] = window.location.hash || TAB_TO_HASH[activeTab];
      
      // Update hash to target tab's last saved hash
      const targetHash = lastTabHashes.current[tab] || TAB_TO_HASH[tab];
      window.location.hash = targetHash;
    }
    setActiveTab(tab);
  };

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
      <DashboardLayout activeTab={activeTab} onTabChange={handleTabChange}>
        {activeTab === 'change-monitor' && <DashboardPage />}
        {activeTab === 'new-monitor' && <NewMonitorPage />}
        {activeTab === 'logs' && <LogPage />}
        {activeTab === 'settings' && <SettingsPage />}
        {activeTab === 'playground' && <PlaygroundPage />}
      </DashboardLayout>
      <ToastProvider />
      <SystemAlertPopup />
    </>
  );
}
