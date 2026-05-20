import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowClockwise, Warning } from '@phosphor-icons/react';

import type { PlaygroundSummary } from './PlaygroundPage/types';
import { fetchPlaygroundSummary } from './PlaygroundPage/api';

// 분리한 서브 컴포넌트 임포트
import { ManualTriggerSection } from './PlaygroundPage/components/ManualTriggerSection';
import { TodayDetectionSection } from './PlaygroundPage/components/TodayDetectionSection';
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
    setTimeout(refetch, 1000);
    console.info('[Playground Trigger]', msg);
  }, [refetch]);

  const today = summary?.today ?? null;
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

      {/* 개발자 전용 경고 문구 */}
      <div className="flex items-start gap-2.5 px-4 py-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5 text-yellow-400">
        <Warning className="w-4 h-4 mt-0.5 shrink-0" />
        <p className="text-xs leading-relaxed">
          개발자의 안내 없이는 플레이그라운드 기능 사용을 지양해주세요.
          수동 트리거 등은 서버 상태에 직접적인 영향을 줌니다.
        </p>
      </div>

      {/* Row 1: Triggers + Today Detection */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ManualTriggerSection onTriggerMsg={handleTriggerMsg} />
        <TodayDetectionSection today={today} />
      </div>

      {/* Row 2: Page Scan History */}
      <PageScanHistorySection pageScan={pageScan} />
    </div>
  );
}

export default PlaygroundPage;
