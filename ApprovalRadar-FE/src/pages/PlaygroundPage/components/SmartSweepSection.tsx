import { useState } from 'react';
import { MagnifyingGlass, Lightning, ArrowClockwise } from '@phosphor-icons/react';
import type { SmartSweepLogEntry, SmartSweepCache } from '../types';
import { triggerJob } from '../api';

interface SmartSweepSectionProps {
  sweepLog: SmartSweepLogEntry[];
  sweepCache: SmartSweepCache | null;
  onTriggerMsg: (msg: string) => void;
}

export function SmartSweepSection({ sweepLog, sweepCache, onTriggerMsg }: SmartSweepSectionProps) {
  const [loading, setLoading] = useState(false);

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

  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
        <MagnifyingGlass size={18} className="text-violet-400" />
        🔬 SmartSweep 실험 모니터
      </h2>
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => handleTrigger('smart_sweep_micro')}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 text-xs font-medium transition-colors border border-violet-600/30 disabled:opacity-40"
        >
          <Lightning size={13} /> Micro Probe (10탐침)
        </button>
        <button
          onClick={() => handleTrigger('smart_sweep_full')}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-xs font-medium transition-colors border border-indigo-600/30 disabled:opacity-40"
        >
          <ArrowClockwise size={13} /> Full Sweep (200seg)
        </button>
      </div>

      {/* 캐시 요약 */}
      {sweepCache && sweepCache.total_cached > 0 && (
        <div className="flex gap-3 mb-4">
          {[
            { label: '탐침 세그먼트', val: sweepCache.total_cached, color: 'text-zinc-300' },
            { label: '🎯 HOT', val: sweepCache.hot, color: 'text-red-400' },
            { label: '📅 WARM', val: sweepCache.warm, color: 'text-amber-400' },
            { label: '❄️ COLD', val: sweepCache.cold, color: 'text-zinc-500' },
          ].map(({ label, val, color }) => (
            <div key={label} className="bg-surface-secondary rounded-lg px-3 py-2 text-center min-w-[70px]">
              <div className={`text-lg font-bold ${color}`}>{val}</div>
              <div className="text-[10px] text-text-muted mt-0.5">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* 실행 이력 */}
      {sweepLog.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs text-text-muted mb-2">최근 {sweepLog.length}회 실행 이력</div>
          {sweepLog.slice(0, 5).map((entry, idx) => (
            <div key={idx} className="bg-surface-secondary rounded-lg px-3 py-2.5 flex items-center gap-4 text-xs">
              <span className="text-text-muted shrink-0 w-[72px]">
                {entry.run_at.slice(11, 19)}
              </span>
              <span className="text-zinc-400 w-[90px] shrink-0">{entry.strategy}</span>
              <span className="text-violet-300">탐침 {entry.probe_calls}회</span>
              <span className={entry.hot_segs > 0 ? 'text-red-400 font-semibold' : 'text-zinc-500'}>
                HOT {entry.hot_segs}
              </span>
              <span className={entry.collected > 0 ? 'text-emerald-400 font-semibold' : 'text-zinc-600'}>
                수집 {entry.collected}건
              </span>
              <span className="text-zinc-600 ml-auto">{entry.elapsed_sec.toFixed(1)}초</span>
            </div>
          ))}
          {sweepLog[0]?.detail.length > 0 && (
            <div className="mt-3 p-2 bg-surface-secondary rounded-lg">
              <div className="text-xs text-text-muted mb-1.5">최근 실행 주목 세그먼트</div>
              {sweepLog[0].detail.map((d, i) => (
                <div key={i} className="flex gap-2 text-xs py-0.5">
                  <span className={d.class === 'HOT' ? 'text-red-400' : 'text-zinc-500'}>
                    {d.class === 'HOT' ? '🎯' : '📅'} {d.seg}
                  </span>
                  <span className="text-zinc-500">first={d.first_chng}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="text-sm text-text-muted">아직 실행 이력 없음 — Micro Probe를 실행해보세요</div>
      )}
    </div>
  );
}
