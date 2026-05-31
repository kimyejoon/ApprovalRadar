import React, { useState, useEffect } from 'react';
import { Broadcast, Sun, Moon, SquaresFour, PlusSquare, Terminal, GearSix, Flask } from '@phosphor-icons/react';
import { Button } from '../ui/button';
import { ServerStatusBadge } from '../ui/ServerStatusBadge';
import { useApiHealthStore } from '@/store/useApiHealthStore';

export type ActiveTab = 'change-monitor' | 'new-monitor' | 'logs' | 'settings' | 'playground';

interface DashboardLayoutProps {
  children: React.ReactNode;
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
}

const NAV_ITEMS: { id: ActiveTab; label: string; icon: React.ElementType }[] = [
  { id: 'change-monitor', label: '변경건 모니터링', icon: SquaresFour },
  { id: 'new-monitor',    label: '신규건 모니터링', icon: PlusSquare },
  { id: 'logs',           label: '로그',          icon: Terminal },
  { id: 'settings',       label: '설정',          icon: GearSix },
  { id: 'playground',     label: '플레이그라운드',   icon: Flask },
];

export function DashboardLayout({ children, activeTab, onTabChange }: DashboardLayoutProps) {
  const [isDark, setIsDark] = useState(false);
  const { status } = useApiHealthStore();

  const STATUS_CONFIG: Record<
    string,
    { label: string; dot: string; text: string }
  > = {
    NORMAL:   { label: '정상',   dot: 'bg-emerald-500', text: 'text-emerald-500' },
    SLOW:     { label: '느림',   dot: 'bg-yellow-400',  text: 'text-yellow-400'  },
    DEGRADED: { label: '저하',   dot: 'bg-orange-500',  text: 'text-orange-500'  },
    UNSTABLE: { label: '불안정', dot: 'bg-red-500',     text: 'text-red-500'     },
    UNKNOWN:  { label: '확인중', dot: 'bg-gray-400',    text: 'text-gray-400'    },
  };

  const STATUS_DESC: Record<string, string> = {
    NORMAL:   '식품안전나라 API 서버가 정상적으로 응답하고 있습니다.',
    SLOW:     '응답이 다소 느립니다. 데이터 수집 속도가 저하될 수 있습니다.',
    DEGRADED: '다수의 타임아웃이 감지됐습니다. 수집 지연이 발생 중입니다.',
    UNSTABLE: 'API 서버가 불안정합니다. WAF 차단 또는 최대 재시도 초과 발생.',
    UNKNOWN:  'SSE 연결 후 첫 PING을 기다리는 중입니다. (최대 5초)',
  };

  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.UNKNOWN;
  const desc = STATUS_DESC[status] ?? STATUS_DESC.UNKNOWN;

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  const PAGE_TITLES: Record<ActiveTab, string> = {
    'change-monitor': '실시간 인허가 변동 모니터링',
    'new-monitor':    '실시간 인허가 신규 등록 모니터링',
    logs:             '시스템 로그 모니터링',
    settings:         '설정',
    playground:       '크롤러 플레이그라운드',
  };

  return (
    <div className="flex h-screen bg-background text-text-primary overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 border-r border-border-standard flex flex-col">
        {/* 로고 */}
        <div className="h-16 flex items-center px-6 border-b border-border-standard">
          <Broadcast className="w-6 h-6 text-brand mr-3" />
          <span className="font-sans font-medium text-lg tracking-tight">인허가Radar</span>
        </div>

        {/* 내비게이션 */}
        <nav className="px-4 py-6 space-y-1">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                id={`nav-${id}`}
                onClick={() => onTabChange(id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-brand/10 text-brand border border-brand/20'
                    : 'text-text-secondary hover:bg-surface hover:text-text-primary border border-transparent'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-brand' : 'text-text-muted'}`} weight={isActive ? 'fill' : 'regular'} />
                {label}
                {id === 'logs' && (
                  <span className="ml-auto w-2 h-2 rounded-full bg-brand animate-pulse" title="WebSocket 실시간" />
                )}
              </button>
            );
          })}
        </nav>

        {/* 외부 API 상태 위젯 */}
        <div className="flex-1 px-4 flex flex-col justify-end pb-6">
          <div className="p-4 rounded-xl border border-border-standard bg-surface shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <span className="relative flex h-2 w-2">
                {status === 'NORMAL' && (
                  <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${cfg.dot} opacity-60`} />
                )}
                <span className={`relative inline-flex rounded-full h-2 w-2 ${cfg.dot}`} />
              </span>
              <span className="text-[10px] font-semibold text-text-muted tracking-wider uppercase">외부 API 상태</span>
            </div>
            <div className={`text-sm font-bold mb-1.5 ${cfg.text}`}>
              외부 API: {cfg.label}
            </div>
            <p className="text-xs text-text-secondary leading-relaxed font-normal">
              {desc}
            </p>
          </div>
        </div>

        {/* 하단 정보 */}
        <div className="p-4 border-t border-border-standard">
          <div className="text-xs text-text-muted">
            Developed By <span className="text-text-secondary font-mono">Sherpa-z</span>
          </div>
          <div className="text-xs text-text-muted">
            ceo@sherpa-z.com
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-border-standard flex items-center justify-between px-8 shrink-0">
          <h1 className="font-sans text-xl tracking-tight m-0">{PAGE_TITLES[activeTab]}</h1>
          
          <div className="flex items-center gap-3">
            {/* 외부 API 서버 상태 배지 */}
            <ServerStatusBadge />
            {/* 다크모드 토글 */}
            <Button variant="ghost" size="sm" className="w-10 h-10 p-0 rounded-full" onClick={() => setIsDark(!isDark)}>
              {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </Button>
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-auto p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
