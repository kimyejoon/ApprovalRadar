import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowClockwise } from '@phosphor-icons/react';

import type { PlaygroundSummary } from './PlaygroundPage/types';
import { fetchPlaygroundSummary } from './PlaygroundPage/api';

// 분리한 서브 컴포넌트 임포트
import { SchedulerSection } from './PlaygroundPage/components/SchedulerSection';
import { ManualTriggerSection } from './PlaygroundPage/components/ManualTriggerSection';
import { TodayDetectionSection } from './PlaygroundPage/components/TodayDetectionSection';
import { TailHistorySection } from './PlaygroundPage/components/TailHistorySection';
import { PageScanHistorySection } from './PlaygroundPage/components/PageScanHistorySection';

export function PlaygroundPage() {
  /**
   * [SSE 이벤트 기반 제로 폴링]
   * refetchInterval을 사용하지 않습니다.
   * useSSE.ts 내에서 'PLAYGROUND_UPDATE' 이벤트 수신 시
   * queryClient.invalidateQueries({ queryKey: ['playgroundSummary'] }) 가 호출되어
   * 이 쿼리가 자동으로 재실행됩니다. (진짜 이벤트 드리븐)
   */
  const { data: summary, refetch } = useQuery<PlaygroundSummary>({
    queryKey: ['playgroundSummary'],
    queryFn: () => fetchPlaygroundSummary(),
    staleTime: Infinity,      // SSE가 갱신을 책임지므로 자동 만료 없음
    refetchOnWindowFocus: false,
  });

  const handleTriggerMsg = useCallback((msg: string) => {
    // 트리거 후 즉시 한 번 refetch해서 빠른 피드백 제공
    setTimeout(refetch, 1000);
    // Toast 대신 콘솔 (필요 시 토스트 스토어로 연결 가능)
    console.info('[Playground Trigger]', msg);
  }, [refetch]);

  const scheduler = summary?.scheduler ?? null;
  const today = summary?.today ?? null;
  const tailHistory = summary?.tail_history?.entries ?? [];
  const pageScan = summary?.page_scan
    ? { total_pages: summary.page_scan.total_pages, scanned_pages: summary.page_scan.scanned_pages, entries: summary.page_scan.entries }
    : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">크롤러 플레이그라운드</h1>
          <p className="text-sm text-text-muted mt-0.5">실시간 크롤러 모니터링 및 수동 제어</p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-border-standard hover:bg-surface transition-colors text-text-secondary"
        >
          <ArrowClockwise className="w-4 h-4" />
          새로고침
        </button>
      </div>

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
    </div>
  );
}

export default PlaygroundPage;
