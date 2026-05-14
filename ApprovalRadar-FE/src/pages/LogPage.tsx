import { useEffect, useRef } from 'react';
import {
  Terminal,
  WifiX,
  WifiHigh,
  Trash,
  PlugsConnected,
  Key,
  CheckCircle,
  XCircle,
  Warning,
  Database,
  ArrowsClockwise,
} from '@phosphor-icons/react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { LogEntry } from '@/hooks/useLogStream';
import { useLogStream } from '@/hooks/useLogStream';
import { fetchKeyStatus, fetchCrawlerStatus } from '@/lib/api';

// ─── 로그 레벨 스타일 ──────────────────────────────────────────────────────

const LEVEL_STYLES: Record<string, string> = {
  DEBUG:    'text-text-muted',
  INFO:     'text-blue-400',
  WARNING:  'text-yellow-400',
  ERROR:    'text-red-500',
  CRITICAL: 'text-red-600 font-bold',
};

const LEVEL_BG: Record<string, string> = {
  WARNING:  'bg-yellow-400/5',
  ERROR:    'bg-red-500/5',
  CRITICAL: 'bg-red-600/10',
};

function LogLine({ entry }: { entry: LogEntry }) {
  const levelStyle = LEVEL_STYLES[entry.level] ?? 'text-text-primary';
  const bgStyle = LEVEL_BG[entry.level] ?? '';
  return (
    <div className={`flex gap-3 px-4 py-0.5 hover:bg-white/5 transition-colors font-mono text-xs leading-5 ${bgStyle}`}>
      <span className="text-text-muted shrink-0 select-none">{entry.timestamp}</span>
      <span className={`w-14 shrink-0 font-semibold ${levelStyle}`}>[{entry.level}]</span>
      <span className="text-text-secondary break-all whitespace-pre-wrap">{entry.message}</span>
    </div>
  );
}

// ─── API 키 상태 카드 ─────────────────────────────────────────────────────

function KeyStatusCard() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['admin-key-status'],
    queryFn: fetchKeyStatus,
    refetchInterval: 30_000,
  });

  const activeCount = data?.keys.filter(k => k.status === 'active').length ?? 0;
  const exhaustedCount = data?.keys.filter(k => k.status === 'exhausted').length ?? 0;
  const errorCount = data?.keys.filter(k => k.status === 'error').length ?? 0;
  const total = data?.total ?? 0;

  const overallStatus = errorCount > 0 ? 'error' : exhaustedCount > 0 ? 'warning' : 'ok';

  return (
    <Card className="border-border-standard bg-surface">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-text-muted flex items-center gap-2">
          <Key className="w-4 h-4" />
          API 키 상태
        </CardTitle>
        <button onClick={() => refetch()} className="text-text-muted hover:text-text-primary transition-colors" title="새로고침">
          <ArrowsClockwise className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading ? (
          <div className="text-xs text-text-muted">점검 중...</div>
        ) : (
          <>
            <div className={`flex items-center gap-2 ${overallStatus === 'ok' ? 'text-brand' : overallStatus === 'warning' ? 'text-yellow-400' : 'text-red-500'}`}>
              {overallStatus === 'ok' && <CheckCircle weight="fill" className="w-5 h-5" />}
              {overallStatus === 'warning' && <Warning weight="fill" className="w-5 h-5" />}
              {overallStatus === 'error' && <XCircle weight="fill" className="w-5 h-5" />}
              <span className="text-2xl font-bold text-text-primary">{activeCount}</span>
              <span className="text-sm text-text-muted">/ {total} 활성</span>
            </div>
            <div className="grid grid-cols-3 gap-1 pt-1">
              <div className="text-center p-1.5 rounded-lg bg-brand/10 border border-brand/20">
                <div className="text-sm font-bold text-brand">{activeCount}</div>
                <div className="text-[10px] text-text-muted">Active</div>
              </div>
              <div className="text-center p-1.5 rounded-lg bg-yellow-400/10 border border-yellow-400/20">
                <div className="text-sm font-bold text-yellow-400">{exhaustedCount}</div>
                <div className="text-[10px] text-text-muted">소진</div>
              </div>
              <div className="text-center p-1.5 rounded-lg bg-red-500/10 border border-red-500/20">
                <div className="text-sm font-bold text-red-500">{errorCount}</div>
                <div className="text-[10px] text-text-muted">오류</div>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── 크롤러 Tail 상태 카드 ────────────────────────────────────────────────

function CrawlerStatusCard() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['admin-crawler-status'],
    queryFn: fetchCrawlerStatus,
    refetchInterval: 60_000,
  });

  const formatTime = (iso: string | null) => {
    if (!iso) return '-';
    return new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  return (
    <Card className="border-border-standard bg-surface">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-text-muted flex items-center gap-2">
          <Database className="w-4 h-4" />
          크롤러 Tail 상태
        </CardTitle>
        <button onClick={() => refetch()} className="text-text-muted hover:text-text-primary transition-colors" title="새로고침">
          <ArrowsClockwise className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading ? (
          <div className="text-xs text-text-muted">조회 중...</div>
        ) : data?.services.length === 0 ? (
          <div className="text-xs text-text-muted">데이터 없음 (부트스트랩 미완료)</div>
        ) : (
          <div className="space-y-2">
            {data?.services.map(svc => (
              <div key={svc.service_id} className="p-2 rounded-lg bg-background border border-border-subtle">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-semibold text-brand">{svc.service_id}</span>
                  <span className="text-xs text-text-muted">{formatTime(svc.updated_at)}</span>
                </div>
                <div className="text-xl font-bold text-text-primary mt-0.5">
                  {svc.last_total_count.toLocaleString()}
                  <span className="text-sm font-normal text-text-muted ml-1">건</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── 메인 로그 페이지 ─────────────────────────────────────────────────────

export function LogPage() {
  const { logs, isConnected, connect, disconnect, clearLogs } = useLogStream();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="flex flex-col h-full gap-4">

      {/* 인디케이터 카드 영역 */}
      <div className="grid grid-cols-2 gap-4 shrink-0">
        <KeyStatusCard />
        <CrawlerStatusCard />
      </div>

      {/* 터미널 헤더 */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-xl font-sans font-medium text-text-primary tracking-tight flex items-center gap-2">
            <Terminal className="w-5 h-5 text-brand" />
            실시간 로그 터미널
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium ${
            isConnected
              ? 'border-brand/30 text-brand bg-brand/5'
              : 'border-border-standard text-text-muted bg-surface'
          }`}>
            {isConnected
              ? <><WifiHigh className="w-3.5 h-3.5" /> 연결됨</>
              : <><WifiX className="w-3.5 h-3.5" /> 연결 안됨</>
            }
          </div>
          <button
            id="log-connect-toggle"
            onClick={isConnected ? disconnect : connect}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
              isConnected
                ? 'border-border-standard text-text-muted hover:text-red-400 hover:border-red-400/30'
                : 'border-brand/30 text-brand hover:bg-brand/10'
            }`}
          >
            <PlugsConnected className="w-3.5 h-3.5" />
            {isConnected ? '연결 해제' : '연결'}
          </button>
          <button
            id="log-clear-btn"
            onClick={clearLogs}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border-standard text-xs font-medium text-text-muted hover:text-red-400 hover:border-red-400/30 transition-all"
          >
            <Trash className="w-3.5 h-3.5" />
            지우기
          </button>
        </div>
      </div>

      {/* 터미널 영역 */}
      <div className="flex-1 rounded-xl border border-border-standard bg-[#0d0d0d] overflow-hidden flex flex-col min-h-0">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10 bg-white/5 shrink-0">
          <span className="w-3 h-3 rounded-full bg-red-500/70" />
          <span className="w-3 h-3 rounded-full bg-yellow-400/70" />
          <span className="w-3 h-3 rounded-full bg-brand/70" />
          <span className="ml-2 font-mono text-xs text-white/30">approvalradar — server logs</span>
          {isConnected && (
            <span className="ml-auto flex items-center gap-1 text-xs text-brand/70 font-mono">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-brand animate-pulse" />
              LIVE
            </span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-white/20">
              <Terminal className="w-10 h-10" />
              <p className="font-mono text-sm">
                {isConnected ? '로그를 기다리는 중...' : '연결 버튼을 눌러 로그 스트림을 시작하세요.'}
              </p>
            </div>
          ) : (
            <div className="py-2">
              {logs.map((entry, i) => <LogLine key={i} entry={entry} />)}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
        <div className="px-4 py-1.5 border-t border-white/10 bg-white/5 shrink-0 flex items-center justify-between">
          <span className="font-mono text-xs text-white/30">{logs.length} lines</span>
          <span className="font-mono text-xs text-white/30">
            {isConnected ? '● CONNECTED' : '○ DISCONNECTED'}
          </span>
        </div>
      </div>
    </div>
  );
}
