import React, { useState, useEffect } from 'react';
import { Broadcast, Sun, Moon } from '@phosphor-icons/react';
import { Button } from '../ui/button';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  return (
    <div className="flex h-screen bg-background text-text-primary overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 border-r border-border-standard flex flex-col">
        <div className="h-16 flex items-center px-6 border-b border-border-standard">
          <Broadcast className="w-6 h-6 text-brand mr-3" />
          <span className="font-sans font-medium text-lg tracking-tight">인허가Radar</span>
        </div>
        <nav className="flex-1 px-4 py-6 space-y-2">
          <a href="#" className="block px-3 py-2 rounded-md bg-surface border border-border-standard text-text-primary text-sm font-medium">
            대시보드
          </a>
          {/* Add more nav items here later if needed */}
        </nav>
        <div className="p-4 border-t border-border-standard">
          <div className="text-xs text-text-muted">
            Last Updated: <span className="text-text-secondary font-mono">10 mins ago</span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-border-standard flex items-center justify-between px-8 shrink-0">
          <h1 className="font-sans text-xl tracking-tight m-0">실시간 인허가 변동 모니터링</h1>
          <Button variant="ghost" size="sm" className="w-10 h-10 p-0 rounded-full" onClick={() => setIsDark(!isDark)}>
            {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </Button>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-auto p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
