import { MagnifyingGlass } from '@phosphor-icons/react';
import type { PageScanEntry } from '../types';

interface PageScanHistorySectionProps {
  pageScan: { total_pages: number; scanned_pages: number; entries: PageScanEntry[] } | null;
}

function formatRelativeTime(isoString: string): string {
  const scannedMs = new Date(isoString).getTime();
  const diffMs = Date.now() - scannedMs;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '방금';
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}시간 전`;
  return `${Math.floor(diffH / 24)}일 전`;
}

export function PageScanHistorySection({ pageScan }: PageScanHistorySectionProps) {
  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
        <MagnifyingGlass className="w-5 h-5 text-orange-400" />
        페이지 스캔 히스토리
      </h2>
      {pageScan ? (
        <div>
          {/* 진행률 바 */}
          <div className="flex items-center gap-4 mb-4">
            <span className="text-sm text-text-secondary">
              전체 {pageScan.total_pages}p 중 <span className="text-brand font-semibold">{pageScan.scanned_pages}p</span> 스캔 완료
            </span>
            <div className="flex-1 h-1.5 bg-border-subtle rounded-full overflow-hidden">
              <div
                className="h-full bg-brand rounded-full transition-all duration-500"
                style={{ width: `${pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100) : 0}%` }}
              />
            </div>
            <span className="text-sm text-text-muted font-mono">
              {pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100).toFixed(0) : 0}%
            </span>
          </div>

          {/* 페이지 카드 그리드 */}
          <div className="grid grid-cols-5 gap-2">
            {(() => {
              const nowMs = Date.now();
              const ONE_HOUR_MS = 60 * 60 * 1000;
              const todayStr = new Date().toISOString().slice(0, 10);

              return pageScan.entries.map((e) => {
                const hasTime = !!e.last_scanned;

                let borderColor: string;
                let bgColor: string;
                let statusLabel: string;
                let statusColor: string;

                if (!hasTime) {
                  borderColor = 'border-border-subtle';
                  bgColor = 'bg-background';
                  statusLabel = '미스캔';
                  statusColor = 'text-text-muted';
                } else {
                  const scannedDate = e.last_scanned!.slice(0, 10);
                  const scannedMs = new Date(e.last_scanned!).getTime();
                  const ageMs = nowMs - scannedMs;

                  if (scannedDate < todayStr) {
                    borderColor = 'border-zinc-600/40';
                    bgColor = 'bg-zinc-800/20';
                    statusLabel = formatRelativeTime(e.last_scanned!);
                    statusColor = 'text-zinc-500';
                  } else if (ageMs < ONE_HOUR_MS) {
                    borderColor = 'border-emerald-500/50';
                    bgColor = 'bg-emerald-500/10';
                    statusLabel = formatRelativeTime(e.last_scanned!);
                    statusColor = 'text-emerald-400';
                  } else {
                    borderColor = 'border-emerald-800/40';
                    bgColor = 'bg-emerald-900/10';
                    statusLabel = formatRelativeTime(e.last_scanned!);
                    statusColor = 'text-emerald-700';
                  }
                }

                return (
                  <div
                    key={e.page_number}
                    className={`flex flex-col items-center justify-between border rounded-lg p-2.5 transition-all ${borderColor} ${bgColor}`}
                    title={`P${e.page_number} (${e.page_start.toLocaleString()}~)${hasTime ? `\n최종 스캔: ${e.last_scanned}` : '\n미스캔'}`}
                  >
                    {/* 페이지 번호 */}
                    <span className="text-[11px] font-bold text-text-muted font-mono">
                      P{e.page_number}
                    </span>

                    {/* 상호명 대역 (가~나) */}
                    <span className="text-base font-bold text-text-primary leading-tight my-1">
                      {e.label ?? '—'}
                    </span>

                    {/* 스캔 시간 */}
                    <span className={`text-[10px] font-medium ${statusColor} leading-tight`}>
                      {statusLabel}
                    </span>
                  </div>
                );
              });
            })()}
          </div>

          {/* 범례 */}
          <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded border border-emerald-500/50 bg-emerald-500/10" />
              1시간 미만
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded border border-emerald-800/40 bg-emerald-900/10" />
              1시간 이상
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded border border-zinc-600/40 bg-zinc-800/20" />
              오늘 이전
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded border border-border-subtle bg-background" />
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
