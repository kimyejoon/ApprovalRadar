import { useEffect, useRef } from 'react';
import {
  Terminal,
  WifiX,
  WifiHigh,
  Trash,
  PlugsConnected,
} from '@phosphor-icons/react';
import type { LogEntry } from '@/hooks/useLogStream';
import { useLogStream } from '@/hooks/useLogStream';

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

export function LogPage() {
  const { logs, isConnected, connect, disconnect, clearLogs } = useLogStream();
  const bottomRef = useRef<HTMLDivElement>(null);

  // 새 로그가 오면 자동 스크롤
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="flex flex-col h-full gap-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h2 className="text-2xl font-sans font-medium text-text-primary tracking-tight flex items-center gap-2">
            <Terminal className="w-6 h-6 text-brand" />
            시스템 로그
          </h2>
          <p className="text-text-muted mt-1 text-sm">
            백엔드 서버 로그를 실시간으로 모니터링합니다.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* 연결 상태 배지 */}
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

          {/* 연결/해제 버튼 */}
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

          {/* 로그 지우기 */}
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
        {/* 터미널 탑 바 */}
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

        {/* 로그 라인들 */}
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
              {logs.map((entry, i) => (
                <LogLine key={i} entry={entry} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* 하단 상태바 */}
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
