import { useEffect, useRef, useState } from 'react';
import {
  Terminal,
  WifiX,
  WifiHigh,
  Trash,
  Key,
  Database,
  ArrowsClockwise,
  DownloadSimple,
  FileText,
} from '@phosphor-icons/react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { LogEntry } from '@/hooks/useLogStream';
import { useLogStream } from '@/hooks/useLogStream';
import { fetchKeyStatus, fetchCrawlerStatus, API_BASE_URL } from '@/lib/api';


// ─── 로그 레벨 스타일 ──────────────────────────────────────────────────────

const LEVEL_STYLES: Record<string, string> = {
  DEBUG: 'text-text-muted',
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-500',
  CRITICAL: 'text-red-600 font-bold',
};

const LEVEL_BG: Record<string, string> = {
  WARNING: 'bg-yellow-400/5',
  ERROR: 'bg-red-500/5',
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
  const accentClass = overallStatus === 'ok' ? 'text-brand' : overallStatus === 'warning' ? 'text-yellow-400' : 'text-red-500';

  return (
    <Card className="flex flex-col justify-center border-border-standard shadow-sm bg-surface-primary relative overflow-hidden min-h-[130px]">
      <CardHeader className="pb-1">
        <CardTitle className="text-sm font-medium text-text-muted flex items-center justify-between">
          <span className="flex items-center gap-2"><Key className="w-4 h-4" />API 키 상태</span>
          <button onClick={() => refetch()} className="text-text-muted hover:text-text-primary transition-colors" title="새로고침">
            <ArrowsClockwise className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-text-muted">점검 중...</div>
        ) : (
          <>
            <div className={`text-4xl font-bold ${accentClass}`}>
              {activeCount}
              <span className="text-sm font-normal text-text-muted ml-2">/ {total} Active</span>
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
    return new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <Card className="flex flex-col justify-center border-border-standard shadow-sm bg-surface-primary relative overflow-hidden min-h-[130px]">
      <CardHeader className="pb-1">
        <CardTitle className="text-sm font-medium text-text-muted flex items-center justify-between">
          <span className="flex items-center gap-2"><Database className="w-4 h-4" />크롤러 Tail</span>
          <button onClick={() => refetch()} className="text-text-muted hover:text-text-primary transition-colors" title="새로고침">
            <ArrowsClockwise className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-xs text-text-muted">조회 중...</div>
        ) : !data?.services.length ? (
          <div className="text-xs text-text-muted">부트스트랩 미완료</div>
        ) : (
          <div className="space-y-1.5">
            {data.services.map(svc => (
              <div key={svc.service_id} className="flex items-baseline justify-between">
                <span className="font-mono text-xs font-medium text-brand">{svc.service_id}</span>
                <span className="text-xl font-bold text-text-primary">
                  {svc.last_total_count.toLocaleString()}
                  <span className="text-xs font-normal text-text-muted ml-1">{formatTime(svc.updated_at)}</span>
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── 로그 파일 다운로드 카드 ──────────────────────────────────────────────

function DownloadLogCard() {
  const [downloading, setDownloading] = useState(false);
  const [lastDownload, setLastDownload] = useState<string | null>(null);
  const todayStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/admin/logs/download`);
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || '로그 파일을 찾을 수 없습니다.');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `approvalradar_${todayStr}.log`;
      a.click();
      URL.revokeObjectURL(url);
      setLastDownload(new Date().toLocaleTimeString('ko-KR'));
    } catch {
      alert('다운로드 중 오류가 발생했습니다.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Card className="flex flex-col justify-center border-border-standard shadow-sm bg-surface-primary relative overflow-hidden min-h-[130px]">
      <CardHeader className="pb-1">
        <CardTitle className="text-sm font-medium text-text-muted flex items-center gap-2">
          <FileText className="w-4 h-4" />
          로그 파일
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2.5">
        <div className="font-mono text-xs text-text-muted">app_{todayStr}.log</div>
        <button
          id="log-download-btn"
          onClick={handleDownload}
          disabled={downloading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-brand/30 text-brand text-xs font-medium hover:bg-brand/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <DownloadSimple className={`w-3.5 h-3.5 ${downloading ? 'animate-bounce' : ''}`} />
          {downloading ? '다운로드 중...' : '오늘 로그 다운로드'}
        </button>
        {lastDownload && (
          <p className="text-[10px] text-text-muted">마지막: {lastDownload}</p>
        )}
      </CardContent>
    </Card>
  );
}

// ─── 메인 로그 페이지 ─────────────────────────────────────────────────────

export function LogPage() {
  const { logs, isConnected, clearLogs } = useLogStream();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="flex flex-col h-full gap-4">

      {/* 인디케이터 카드 영역 */}
      <div className="grid grid-cols-3 gap-4 shrink-0">
        <KeyStatusCard />
        <CrawlerStatusCard />
        <DownloadLogCard />
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
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium ${isConnected
            ? 'border-brand/30 text-brand bg-brand/5'
            : 'border-border-standard text-text-muted bg-surface'
            }`}>
            {isConnected
              ? <><WifiHigh className="w-3.5 h-3.5" /> 연결됨</>
              : <><WifiX className="w-3.5 h-3.5" /> 재연결 중...</>
            }
          </div>
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
