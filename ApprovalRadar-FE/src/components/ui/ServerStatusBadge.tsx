import React, { useEffect, useRef, useState } from 'react';
import { useApiHealthStore } from '@/store/useApiHealthStore';

// ─── 상태별 시각 설정 ──────────────────────────────────────────────────────────

type HealthStatus = 'NORMAL' | 'SLOW' | 'DEGRADED' | 'UNSTABLE' | 'UNKNOWN';

const STATUS_CONFIG: Record<
  HealthStatus,
  { label: string; dot: string; text: string }
> = {
  NORMAL:   { label: '정상',   dot: 'bg-emerald-500', text: 'text-emerald-500' },
  SLOW:     { label: '느림',   dot: 'bg-yellow-400',  text: 'text-yellow-400'  },
  DEGRADED: { label: '저하',   dot: 'bg-orange-500',  text: 'text-orange-500'  },
  UNSTABLE: { label: '불안정', dot: 'bg-red-500',     text: 'text-red-500'     },
  UNKNOWN:  { label: '확인중', dot: 'bg-gray-400',    text: 'text-gray-400'    },
};

const STATUS_DESC: Record<HealthStatus, string> = {
  NORMAL:   '식품안전나라 API 서버가 정상적으로 응답하고 있습니다.',
  SLOW:     '응답이 다소 느립니다. 데이터 수집 속도가 저하될 수 있습니다.',
  DEGRADED: '다수의 타임아웃이 감지됐습니다. 수집 지연이 발생 중입니다.',
  UNSTABLE: 'API 서버가 불안정합니다. WAF 차단 또는 최대 재시도 초과 발생.',
  UNKNOWN:  'SSE 연결 후 첫 PING을 기다리는 중입니다. (최대 5초)',
};

// ─── 컴포넌트 ─────────────────────────────────────────────────────────────────

export function ServerStatusBadge() {
  const { status, metrics, window_seconds, last_updated } = useApiHealthStore();
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  // 외부 클릭 시 팝오버 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const cfg = STATUS_CONFIG[status as HealthStatus] ?? STATUS_CONFIG.UNKNOWN;

  return (
    <div className="relative" ref={popoverRef}>
      {/* ── 배지 버튼 ─────────────────────────────────────────────────────── */}
      <button
        id="server-status-badge"
        onClick={() => setIsOpen((o) => !o)}
        title="외부 API 서버 상태 보기"
        className={`
          flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium
          transition-all hover:opacity-80 cursor-pointer
          bg-surface border-border-standard
        `}
      >
        {/* 애니메이션 도트 */}
        <span className="relative flex h-2 w-2">
          {status === 'NORMAL' && (
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${cfg.dot} opacity-60`} />
          )}
          <span className={`relative inline-flex rounded-full h-2 w-2 ${cfg.dot}`} />
        </span>
        <span className={cfg.text}>{cfg.label}</span>
      </button>

      {/* ── 팝오버 ────────────────────────────────────────────────────────── */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-72 z-50 bg-background border border-border-standard rounded-2xl shadow-2xl overflow-hidden">
          {/* 헤더 */}
          <div className="px-4 py-3 border-b border-border-standard bg-surface flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              {status === 'NORMAL' && (
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${cfg.dot} opacity-60`} />
              )}
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${cfg.dot}`} />
            </span>
            <span className={`text-sm font-semibold ${cfg.text}`}>
              외부 API: {cfg.label}
            </span>
          </div>

          {/* 설명 */}
          <div className="px-4 py-3 border-b border-border-standard">
            <p className="text-xs text-text-secondary leading-relaxed">
              {STATUS_DESC[status as HealthStatus]}
            </p>
          </div>

          {/* 메트릭 */}
          {metrics && (
            <div className="px-4 py-3 grid grid-cols-2 gap-x-4 gap-y-2.5">
              <MetricRow label="평균 응답시간" value={`${metrics.avg_response_ms.toLocaleString()} ms`} />
              <MetricRow label="성공률" value={`${metrics.success_rate}%`} />
              <MetricRow label="타임아웃" value={`${metrics.timeout_count}건`} warn={metrics.timeout_count > 0} />
              <MetricRow label="WAF 차단" value={`${metrics.waf_block_count}건`} warn={metrics.waf_block_count > 0} />
              <MetricRow label="최대재시도 초과" value={`${metrics.max_retry_count}건`} warn={metrics.max_retry_count > 0} />
              <MetricRow label="집계 API 호출" value={`${metrics.total_calls}건`} />
            </div>
          )}

          {/* 푸터 */}
          <div className="px-4 py-2.5 border-t border-border-standard bg-surface">
            <p className="text-[10px] text-text-muted">
              최근 {window_seconds / 60}분 기준 · SSE PING 5초 갱신
              {last_updated && (
                <> · 마지막: {new Date(last_updated).toLocaleTimeString('ko-KR')}</>
              )}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 서브 컴포넌트 ─────────────────────────────────────────────────────────────

function MetricRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium text-text-muted">{label}</span>
      <span className={`text-xs font-semibold ${warn ? 'text-orange-500' : 'text-text-primary'}`}>
        {value}
      </span>
    </div>
  );
}
