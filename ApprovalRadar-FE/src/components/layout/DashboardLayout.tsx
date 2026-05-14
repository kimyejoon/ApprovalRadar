import React, { useState, useEffect } from 'react';
import { Broadcast, Sun, Moon, SquaresFour, Terminal } from '@phosphor-icons/react';
import { Button } from '../ui/button';
import { KeyStatusIndicator } from '../ui/KeyStatusIndicator';

export type ActiveTab = 'dashboard' | 'logs';

interface DashboardLayoutProps {
  children: React.ReactNode;
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
}

const NAV_ITEMS: { id: ActiveTab; label: string; icon: React.ElementType }[] = [
  { id: 'dashboard', label: '대시보드', icon: SquaresFour },
  { id: 'logs',      label: '로그',    icon: Terminal },
];

export function DashboardLayout({ children, activeTab, onTabChange }: DashboardLayoutProps) {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  const PAGE_TITLES: Record<ActiveTab, string> = {
    dashboard: '실시간 인허가 변동 모니터링',
    logs:      '시스템 로그 모니터링',
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
        <nav className="flex-1 px-4 py-6 space-y-1">
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
            {/* API 키 상태 인디케이터 */}
            <KeyStatusIndicator />

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
