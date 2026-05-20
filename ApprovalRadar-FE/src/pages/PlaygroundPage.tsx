import { useState, useEffect, useCallback } from 'react';
import { ArrowClockwise } from '@phosphor-icons/react';
import { 
  fetchSchedulerStatus, 
  fetchTodayDetection, 
  fetchTailHistory, 
  fetchPageScanHistory 
} from '@/features/playground/api';
import { 
  SchedulerStatus, 
  TodayDetection, 
  TailHistoryEntry, 
  PageScanHistory 
} from '@/features/playground/types';
import { SchedulerCard } from '@/features/playground/components/SchedulerCard';
import { ManualTriggerCard } from '@/features/playground/components/ManualTriggerCard';
import { TodayDetectionCard } from '@/features/playground/components/TodayDetectionCard';
import { TailHistoryCard } from '@/features/playground/components/TailHistoryCard';
import { PageScanHistoryCard } from '@/features/playground/components/PageScanHistoryCard';

export function PlaygroundPage() {
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [today, setToday] = useState<TodayDetection | null>(null);
  const [tailHistory, setTailHistory] = useState<TailHistoryEntry[]>([]);
  const [pageScan, setPageScan] = useState<PageScanHistory | null>(null);

  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [sched, det, tail, pages] = await Promise.all([
        fetchSchedulerStatus(),
        fetchTodayDetection(),
        fetchTailHistory(),
        fetchPageScanHistory(),
      ]);
      setScheduler(sched);
      setToday(det);
      setTailHistory(tail);
      setPageScan(pages);
    } catch (e) {
      console.error('Playground refresh failed:', e);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
    const timer = setInterval(refresh, 10000); // 10초 자동 갱신
    return () => clearInterval(timer);
  }, [refresh]);

  const handleMessage = (msg: string) => {
    setTriggerMsg(msg);
    setTimeout(() => setTriggerMsg(null), 5000);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">크롤러 플레이그라운드</h1>
          <p className="text-sm text-text-muted mt-0.5">실시간 크롤러 모니터링 및 수동 제어</p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-border-standard hover:bg-surface transition-colors text-text-secondary"
        >
          <ArrowClockwise className="w-4 h-4" />
          새로고침
        </button>
      </div>

      {/* Toast */}
      {triggerMsg && (
        <div className="fixed top-4 right-4 z-50 bg-brand text-white px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium animate-in slide-in-from-top-2">
          {triggerMsg}
        </div>
      )}

      {/* Row 1: Scheduler + Triggers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SchedulerCard scheduler={scheduler} />
        <ManualTriggerCard onMessage={handleMessage} />
      </div>

      {/* Row 2: Today Detection + Tail History Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TodayDetectionCard today={today} />
        <TailHistoryCard tailHistory={tailHistory} />
      </div>

      {/* Row 3: Page Scan History */}
      <PageScanHistoryCard pageScan={pageScan} />
    </div>
  );
}
