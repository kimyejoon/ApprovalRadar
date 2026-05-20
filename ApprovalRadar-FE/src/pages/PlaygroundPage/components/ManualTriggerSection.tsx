import { useState } from 'react';
import { Lightning, MagnifyingGlass, Play } from '@phosphor-icons/react';
import { triggerJob, triggerRangeScan } from '../api';

interface ManualTriggerSectionProps {
  onTriggerMsg: (msg: string) => void;
}

export function ManualTriggerSection({ onTriggerMsg }: ManualTriggerSectionProps) {
  const [loading, setLoading] = useState(false);
  const [rangeStart, setRangeStart] = useState<string>('1');
  const [rangeEnd, setRangeEnd] = useState<string>('10000');

  const handleTrigger = async (jobType: string) => {
    setLoading(true);
    try {
      const result = await triggerJob(jobType);
      onTriggerMsg(result.message);
    } catch {
      onTriggerMsg('트리거 실패');
    } finally {
      setLoading(false);
    }
  };

  const handleRangeScanSubmit = async () => {
    const s = parseInt(rangeStart, 10);
    const e = parseInt(rangeEnd, 10);
    if (isNaN(s) || isNaN(e) || s < 1 || e < s) {
      onTriggerMsg('잘못된 범위입니다');
      return;
    }
    setLoading(true);
    try {
      const result = await triggerRangeScan(s, e);
      onTriggerMsg(result.message);
    } catch {
      onTriggerMsg('Range Scan 트리거 실패');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
        <Lightning className="w-5 h-5 text-yellow-500" />
        수동 트리거
      </h2>
      <p className="text-xs text-text-muted mb-4">사이클 사이 Term에서 즉시 실행합니다.</p>
      <div className="grid grid-cols-1 gap-3">
        <button
          onClick={() => handleTrigger('scraper')}
          disabled={loading}
          className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-green-500/30 bg-green-500/5 hover:bg-green-500/10 transition-all text-sm font-medium text-green-400 disabled:opacity-50"
        >
          <MagnifyingGlass className="w-4 h-4" />
          Oldest-First Scan 즉시 실행
          <span className="text-xs text-text-muted ml-1">(Scraper 1회 실행)</span>
        </button>
      </div>

      {/* Range Scan */}
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
            onClick={handleRangeScanSubmit}
            disabled={loading}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-orange-400/30 bg-orange-400/5 hover:bg-orange-400/10 transition-all text-sm font-medium text-orange-500 disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            스캔
          </button>
        </div>
        <p className="text-[10px] text-text-muted mt-1.5">
          레코드 번호 범위. 예: 1~5000 = 1~5p
        </p>
      </div>
    </div>
  );
}
