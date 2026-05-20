import { useState, useEffect, useCallback } from 'react';
import { ArrowClockwise } from '@phosphor-icons/react';

// 타입 및 API 임포트
import type {
  SchedulerStatus,
  TodayDetection,
  TailHistoryEntry,
  PageScanEntry,
  SmartSweepLogEntry,
  SmartSweepCache,
} from './PlaygroundPage/types';
import {
  fetchSchedulerStatus,
  fetchTodayDetection,
  fetchTailHistory,
  fetchPageScanHistory,
  fetchSmartSweepStatus,
  fetchSmartSweepCache,
} from './PlaygroundPage/api';

// 분리한 서브 컴포넌트 임포트
import { SchedulerSection } from './PlaygroundPage/components/SchedulerSection';
import { ManualTriggerSection } from './PlaygroundPage/components/ManualTriggerSection';
import { TodayDetectionSection } from './PlaygroundPage/components/TodayDetectionSection';
import { TailHistorySection } from './PlaygroundPage/components/TailHistorySection';
import { PageScanHistorySection } from './PlaygroundPage/components/PageScanHistorySection';
import { SmartSweepSection } from './PlaygroundPage/components/SmartSweepSection';

export function PlaygroundPage() {
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [today, setToday] = useState<TodayDetection | null>(null);
  const [tailHistory, setTailHistory] = useState<TailHistoryEntry[]>([]);
  const [pageScan, setPageScan] = useState<{ total_pages: number; scanned_pages: number; entries: PageScanEntry[] } | null>(null);
  const [sweepLog, setSweepLog] = useState<SmartSweepLogEntry[]>([]);
  const [sweepCache, setSweepCache] = useState<SmartSweepCache | null>(null);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  const handleTriggerMsg = (msg: string) => {
    setTriggerMsg(msg);
    setTimeout(() => setTriggerMsg(null), 5000);
  };

  const refresh = useCallback(async () => {
    try {
      const [sched, det, tail, pages, swLog, swCache] = await Promise.all([
        fetchSchedulerStatus(),
        fetchTodayDetection(),
        fetchTailHistory(),
        fetchPageScanHistory(),
        fetchSmartSweepStatus(),
        fetchSmartSweepCache(),
      ]);
      setScheduler(sched);
      setToday(det);
      setTailHistory(tail);
      setPageScan(pages);
      setSweepLog(swLog.entries);
      setSweepCache(swCache);
    } catch (e) {
      console.error('Playground refresh failed:', e);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

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
        <SchedulerSection scheduler={scheduler} />
        <ManualTriggerSection onTriggerMsg={handleTriggerMsg} />
      </div>

      {/* Row 2: Today Detection + Tail History Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TodayDetectionSection today={today} />
        <TailHistorySection tailHistory={tailHistory} />
      </div>

      {/* Row 3: Page Scan History */}
      <PageScanHistorySection pageScan={pageScan} />

      {/* SmartSweep 모니터 카드 */}
      <SmartSweepSection
        sweepLog={sweepLog}
        sweepCache={sweepCache}
        onTriggerMsg={handleTriggerMsg}
      />
    </div>
  );
}
export default PlaygroundPage;
