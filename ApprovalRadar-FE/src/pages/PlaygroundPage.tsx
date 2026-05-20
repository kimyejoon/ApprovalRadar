import { ArrowClockwise } from '@phosphor-icons/react';
import { usePlayground } from '../features/playground/hooks/usePlayground';
import {
  SchedulerStatusCard,
  TriggerCard,
  TodayDetectionCard,
  TailHistoryChartCard,
  PageScanHistoryCard,
} from '../features/playground/components';

export function PlaygroundPage() {
  const {
    scheduler,
    today,
    tailHistory,
    pageScan,
    triggerMsg,
    loading,
    rangeStart,
    rangeEnd,
    setRangeStart,
    setRangeEnd,
    refresh,
    handleTrigger,
    handleRangeScan,
  } = usePlayground();

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
        <SchedulerStatusCard scheduler={scheduler} />
        <TriggerCard
          loading={loading}
          rangeStart={rangeStart}
          rangeEnd={rangeEnd}
          setRangeStart={setRangeStart}
          setRangeEnd={setRangeEnd}
          onTrigger={handleTrigger}
          onRangeScan={handleRangeScan}
        />
      </div>

      {/* Row 2: Today Detection + Tail History Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TodayDetectionCard today={today} />
        <TailHistoryChartCard tailHistory={tailHistory} />
      </div>

      {/* Row 3: Page Scan History */}
      <PageScanHistoryCard pageScan={pageScan} />
    </div>
  );
}
