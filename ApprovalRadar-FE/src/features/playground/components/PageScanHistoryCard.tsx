import { MagnifyingGlass } from '@phosphor-icons/react';
import { Card } from './ui/Card';
import { SectionTitle } from './ui/SectionTitle';
import { PageScanHistory } from '../types';

interface Props {
  pageScan: PageScanHistory | null;
}

export function PageScanHistoryCard({ pageScan }: Props) {
  return (
    <Card>
      <SectionTitle icon={<MagnifyingGlass className="w-5 h-5 text-orange-400" />} title="페이지 스캔 히스토리" />
      {pageScan ? (
        <div>
          <div className="flex items-center gap-4 mb-4">
            <span className="text-sm text-text-secondary">
              전체 {pageScan.total_pages}p 중 <span className="text-brand font-semibold">{pageScan.scanned_pages}p</span> 스캔 완료
            </span>
            <div className="flex-1 h-2 bg-border-subtle rounded-full overflow-hidden">
              <div
                className="h-full bg-brand rounded-full transition-all"
                style={{ width: `${pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100) : 0}%` }}
              />
            </div>
            <span className="text-sm text-text-muted font-mono">
              {pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100).toFixed(1) : 0}%
            </span>
          </div>

          <div className="flex flex-wrap gap-[2px]">
            {(() => {
              // eslint-disable-next-line react-hooks/purity
              const nowMs = Date.now();
              const ONE_HOUR_MS = 60 * 60 * 1000;
              const todayStr = new Date().toISOString().slice(0, 10);

              return pageScan.entries.map((e) => {
                const hasTime = !!e.last_scanned;
                const hasFP = !!e.fingerprint;

                let colorClass: string;
                if (!hasFP) {
                  colorClass = 'bg-border-subtle hover:bg-border-standard';
                } else if (!hasTime) {
                  colorClass = 'bg-zinc-600/50 hover:bg-zinc-500/60';
                } else {
                  const scannedDate = e.last_scanned!.slice(0, 10);
                  const scannedMs = new Date(e.last_scanned!).getTime();
                  const ageMs = nowMs - scannedMs;

                  if (scannedDate < todayStr) {
                    colorClass = 'bg-zinc-600/50 hover:bg-zinc-500/60';
                  } else if (ageMs < ONE_HOUR_MS) {
                    colorClass = 'bg-emerald-500 hover:bg-emerald-400';
                  } else {
                    colorClass = 'bg-emerald-800/70 hover:bg-emerald-700/80';
                  }
                }

                return (
                  <div
                    key={e.page_number}
                    className={`w-3 h-3 rounded-[2px] transition-colors cursor-pointer ${colorClass}`}
                    title={`P${e.page_number} (${e.page_start.toLocaleString()}~)\n${hasFP ? `FP: ${e.fingerprint}` : '미스캔'}${hasTime ? `\n최종 스캔: ${e.last_scanned}` : ''}`}
                  />
                );
              });
            })()}
          </div>
          <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-[2px] bg-emerald-500" />
              오늘 스캔 (1h 미만)
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-[2px] bg-emerald-800/70" />
              오늘 스캔 (1h 이상)
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-[2px] bg-zinc-600/50" />
              오늘 이전 스캔
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-[2px] bg-border-subtle" />
              미스캔
            </div>
          </div>
        </div>
      ) : (
        <div className="text-sm text-text-muted">로딩 중...</div>
      )}
    </Card>
  );
}
