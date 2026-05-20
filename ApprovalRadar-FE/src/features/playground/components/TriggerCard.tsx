import { Lightning, ClockCounterClockwise, RocketLaunch, Broadcast, MagnifyingGlass, Play } from '@phosphor-icons/react';
import { Card, SectionTitle } from './Shared';

interface TriggerCardProps {
  loading: boolean;
  rangeStart: string;
  rangeEnd: string;
  setRangeStart: (val: string) => void;
  setRangeEnd: (val: string) => void;
  onTrigger: (jobType: string) => void;
  onRangeScan: () => void;
}

export function TriggerCard({
  loading,
  rangeStart,
  rangeEnd,
  setRangeStart,
  setRangeEnd,
  onTrigger,
  onRangeScan,
}: TriggerCardProps) {
  return (
    <Card>
      <SectionTitle icon={<Lightning className="w-5 h-5 text-yellow-500" />} title="수동 트리거" />
      <p className="text-xs text-text-muted mb-4">사이클 사이 Term에서 즉시 실행합니다.</p>
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => onTrigger('oldest_first_scan')}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-green-500/30 bg-green-500/5 hover:bg-green-500/10 transition-all text-sm font-medium text-green-400 disabled:opacity-50 col-span-2"
        >
          <ClockCounterClockwise className="w-4 h-4" />
          Oldest-First Scan <span className="text-xs text-text-muted ml-1">(연식 1h↑ 페이지 전수 스캔)</span>
        </button>
        <button
          onClick={() => onTrigger('boost_scan')}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-brand/30 bg-brand/5 hover:bg-brand/10 transition-all text-sm font-medium text-brand disabled:opacity-50"
        >
          <RocketLaunch className="w-4 h-4" />
          Boost Scan
        </button>
        <button
          onClick={() => onTrigger('tail_ping')}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-border-standard bg-background hover:bg-surface transition-all text-sm font-medium text-text-primary disabled:opacity-50"
        >
          <Broadcast className="w-4 h-4 text-purple-400" />
          Tail Ping
        </button>
        <button
          onClick={() => onTrigger('scraper')}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-border-standard bg-background hover:bg-surface transition-all text-sm font-medium text-text-primary disabled:opacity-50"
        >
          <MagnifyingGlass className="w-4 h-4 text-orange-400" />
          Scraper
        </button>
      </div>

      <div className="mt-4 pt-4 border-t border-border-subtle">
        <p className="text-xs font-medium text-text-secondary mb-2">🎯 범위 지정 스캔</p>
        <div className="flex items-center gap-2">
          <input
            type="number"
            value={rangeStart}
            onChange={(e) => setRangeStart(e.target.value)}
            placeholder="시작"
            className="w-28 px-3 py-2 rounded-lg border border-border-standard bg-background text-sm text-text-primary text-right font-mono focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <span className="text-text-muted text-sm">~</span>
          <input
            type="number"
            value={rangeEnd}
            onChange={(e) => setRangeEnd(e.target.value)}
            placeholder="종료"
            className="w-28 px-3 py-2 rounded-lg border border-border-standard bg-background text-sm text-text-primary text-right font-mono focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <button
            onClick={onRangeScan}
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-orange-400/30 bg-orange-400/5 hover:bg-orange-400/10 transition-all text-sm font-medium text-orange-500 disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            스캔
          </button>
        </div>
        <p className="text-[10px] text-text-muted mt-1.5">
          레코드 번호 범위 (1~952,999). 예: 940001~952999 = 마지막 13p
        </p>
      </div>
    </Card>
  );
}
