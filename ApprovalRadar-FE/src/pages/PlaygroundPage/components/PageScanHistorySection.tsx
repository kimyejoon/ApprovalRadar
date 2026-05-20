import { MagnifyingGlass, SpinnerGap } from '@phosphor-icons/react';
import type { PageScanEntry } from '../types';
import { useScanProgressStore } from '@/store/useScanProgressStore';

interface PageScanHistorySectionProps {
  pageScan: { total_pages: number; scanned_pages: number; entries: PageScanEntry[] } | null;
}

function formatRelativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '방금';
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}시간 전`;
  return `${Math.floor(diffH / 24)}일 전`;
}

export function PageScanHistorySection({ pageScan }: PageScanHistorySectionProps) {
  const { cycle, pages: livePages } = useScanProgressStore();
  const isScanning = cycle !== null && cycle.pages_done < cycle.pages_total;

  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
        <MagnifyingGlass className="w-5 h-5 text-orange-400" />
        페이지 스캔 히스토리
        {isScanning && (
          <span className="flex items-center gap-1.5 text-xs font-normal text-emerald-400 ml-auto">
            <SpinnerGap className="w-3.5 h-3.5 animate-spin" />
            스캔 진행 중
          </span>
        )}
      </h2>

      {/* ── 사이클 진행 현황 패널 ── */}
      {cycle && (
        <div className="mb-4 px-3 py-2.5 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs flex flex-wrap gap-x-5 gap-y-1 text-text-secondary">
          <span>⏱ 소요 <span className="text-text-primary font-mono font-semibold">{cycle.elapsed_sec}초</span></span>
          <span>🔑 API <span className="text-text-primary font-mono font-semibold">{cycle.api_calls}회</span></span>
          <span>📄 진행 <span className="text-text-primary font-mono font-semibold">{cycle.pages_done}/{cycle.pages_total}p</span></span>
          {cycle.est_remaining_min > 0 && (
            <span>⏳ 잔여 <span className="text-text-primary font-mono font-semibold">~{cycle.est_remaining_min}분</span></span>
          )}
        </div>
      )}

      {pageScan ? (
        <div>
          {/* 진행률 바 */}
          <div className="flex items-center gap-3 mb-3">
            <span className="text-sm text-text-secondary whitespace-nowrap">
              {pageScan.total_pages}p 중 <span className="text-brand font-semibold">{pageScan.scanned_pages}p</span>
            </span>
            <div className="flex-1 h-1.5 bg-border-subtle rounded-full overflow-hidden">
              <div
                className="h-full bg-brand rounded-full transition-all duration-500"
                style={{ width: `${pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100) : 0}%` }}
              />
            </div>
            <span className="text-sm text-text-muted font-mono whitespace-nowrap">
              {pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100).toFixed(1) : 0}%
            </span>
          </div>

          {/* 953p 히트맵 */}
          <div className="flex flex-wrap gap-[2px]">
            {(() => {
              const nowMs = Date.now();
              const ONE_HOUR_MS = 60 * 60 * 1000;
              const todayStr = new Date().toISOString().slice(0, 10);

              return pageScan.entries.map((e) => {
                const hasTime = !!e.last_scanned;
                const live = livePages[e.page_number];
                const label = e.label ?? '—';

                let colorClass: string;
                let tooltip: string;

                if (!hasTime) {
                  colorClass = 'bg-border-subtle hover:bg-zinc-600/40';
                  tooltip = `P${e.page_number} [${label}]\n(${e.page_start.toLocaleString()}~)\n미스캔`;
                } else {
                  const scannedDate = e.last_scanned!.slice(0, 10);
                  const ageMs = nowMs - new Date(e.last_scanned!).getTime();
                  const relTime = formatRelativeTime(e.last_scanned!);

                  if (scannedDate < todayStr) {
                    colorClass = 'bg-zinc-600/50 hover:bg-zinc-500/60';
                  } else if (ageMs < ONE_HOUR_MS) {
                    colorClass = 'bg-emerald-500 hover:bg-emerald-400';
                  } else {
                    colorClass = 'bg-emerald-800/70 hover:bg-emerald-700/80';
                  }

                  const liveStr = live?.stats
                    ? `\n오늘 ${live.stats.today}건 · 어제 ${live.stats.yesterday}건\n신규 ${live.stats.new_indexed}건 · 중복 ${live.stats.skipped_dup}건`
                    : '';
                  tooltip = `P${e.page_number} [${label}]\n(${e.page_start.toLocaleString()}~)\n${relTime}${liveStr}`;
                }

                return (
                  <div
                    key={e.page_number}
                    className={`w-2.5 h-2.5 rounded-[1px] transition-colors cursor-pointer flex-shrink-0 ${colorClass}`}
                    title={tooltip}
                  />
                );
              });
            })()}
          </div>

          {/* 범례 */}
          <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-[1px] bg-emerald-500" />
              1시간 미만
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-[1px] bg-emerald-800/70" />
              1시간 이상
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-[1px] bg-zinc-600/50" />
              오늘 이전
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-[1px] bg-border-subtle" />
              미스캔
            </div>
          </div>
        </div>
      ) : (
        <div className="text-sm text-text-muted">로딩 중...</div>
      )}
    </div>
  );
}
