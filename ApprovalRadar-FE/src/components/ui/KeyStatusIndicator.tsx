import { Key, CheckCircle, XCircle, Warning, ArrowsClockwise } from '@phosphor-icons/react';
import { useKeyStatus } from '@/hooks/useKeyStatus';
import type { KeyStatusItem } from '@/lib/api';
import { useState, useRef, useEffect } from 'react';

function StatusDot({ status }: { status: KeyStatusItem['status'] }) {
  const colors = {
    active: 'bg-brand',
    exhausted: 'bg-yellow-400',
    error: 'bg-red-500',
  };
  const pulse = status === 'active' ? 'animate-pulse' : '';
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${colors[status]} ${pulse}`} />
  );
}

export function KeyStatusIndicator() {
  const { data, isLoading, lastUpdated, activeCount, exhaustedCount, errorCount, totalCount, refresh } = useKeyStatus();
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // 바깥 클릭 시 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const overallStatus = errorCount > 0 ? 'error' : exhaustedCount > 0 ? 'warning' : 'ok';

  const badge = {
    ok: { icon: <CheckCircle weight="fill" className="w-4 h-4 text-brand" />, label: `${activeCount}/${totalCount} Active`, cls: 'text-brand border-brand/30' },
    warning: { icon: <Warning weight="fill" className="w-4 h-4 text-yellow-400" />, label: `${exhaustedCount}개 소진`, cls: 'text-yellow-400 border-yellow-400/30' },
    error: { icon: <XCircle weight="fill" className="w-4 h-4 text-red-500" />, label: `${errorCount}개 오류`, cls: 'text-red-500 border-red-500/30' },
  }[overallStatus];

  return (
    <div className="relative" ref={ref}>
      <button
        id="key-status-indicator"
        onClick={() => setIsOpen(v => !v)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-mono font-medium transition-all hover:opacity-80 ${badge.cls} bg-transparent`}
        title="API 키 상태 (클릭하여 상세보기)"
      >
        <Key className="w-3.5 h-3.5" />
        {isLoading ? <span className="opacity-50">점검 중...</span> : badge.label}
        {badge.icon}
      </button>

      {isOpen && data && (
        <div className="absolute right-0 top-10 z-50 w-72 rounded-xl border border-border-standard bg-surface shadow-2xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Key className="w-4 h-4 text-text-muted" />
              <span className="text-sm font-medium text-text-primary">API 키 상태</span>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); refresh(); }}
              className="text-text-muted hover:text-text-primary transition-colors"
              title="새로고침"
            >
              <ArrowsClockwise className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-2">
            {data.keys.map(key => (
              <div key={key.index} className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-background border border-border-subtle">
                <div className="flex items-center gap-2">
                  <StatusDot status={key.status} />
                  <span className="font-mono text-xs text-text-secondary">{key.masked_key}</span>
                </div>
                <span className={`text-xs font-medium ${
                  key.status === 'active' ? 'text-brand' :
                  key.status === 'exhausted' ? 'text-yellow-400' : 'text-red-500'
                }`}>
                  {key.status_label}
                </span>
              </div>
            ))}
          </div>

          {lastUpdated && (
            <p className="text-xs text-text-muted text-right">
              마지막 갱신: {lastUpdated.toLocaleTimeString('ko-KR')} (30초 주기)
            </p>
          )}
        </div>
      )}
    </div>
  );
}
