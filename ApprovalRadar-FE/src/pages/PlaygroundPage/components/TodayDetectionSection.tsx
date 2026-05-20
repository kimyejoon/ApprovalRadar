import { Play } from '@phosphor-icons/react';
import type { TodayDetection } from '../types';

interface TodayDetectionSectionProps {
  today: TodayDetection | null;
}

export function TodayDetectionSection({ today }: TodayDetectionSectionProps) {
  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
        <Play className="w-5 h-5 text-red-400" />
        오늘 감지 현황
      </h2>
      {today ? (
        <div>
          <div className="grid grid-cols-4 gap-3 mb-4">
            <div className="text-center p-3 rounded-lg bg-background">
              <div className="text-2xl font-bold text-brand">{today.today_count}</div>
              <div className="text-xs text-text-muted mt-1">오늘 변동건</div>
            </div>
            <div className="text-center p-3 rounded-lg bg-background">
              <div className="text-2xl font-bold text-yellow-400">{today.yesterday_count}</div>
              <div className="text-xs text-text-muted mt-1">어제 변동건</div>
            </div>
            <div className="text-center p-3 rounded-lg bg-background">
              <div className="text-2xl font-bold text-text-primary">{today.total_records.toLocaleString()}</div>
              <div className="text-xs text-text-muted mt-1">전체 레코드</div>
            </div>
            <div className="text-center p-3 rounded-lg bg-background">
              <div className="text-2xl font-bold text-blue-400">{today.scan_coverage_pct}%</div>
              <div className="text-xs text-text-muted mt-1">FP 커버리지</div>
            </div>
          </div>

          {/* Recent Detections */}
          {today.recent_detections.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs font-medium text-text-muted mb-2">최근 감지 (오늘+어제)</h3>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {today.recent_detections.map((d, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-1.5 rounded bg-background text-xs">
                    <span className="text-text-primary truncate max-w-[40%]">{d.business_name}</span>
                    <span className="text-text-muted">{d.industry_type}</span>
                    <span className="text-brand font-mono">{d.update_type || '—'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="text-sm text-text-muted">로딩 중...</div>
      )}
    </div>
  );
}
