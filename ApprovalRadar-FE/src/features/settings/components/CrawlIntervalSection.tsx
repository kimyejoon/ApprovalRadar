import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Timer, CheckCircle, ArrowsClockwise } from '@phosphor-icons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchCrawlInterval, updateCrawlInterval } from '@/lib/api';

const PRESET_MINUTES = [5, 10, 15, 30, 60, 120] as const;

export function CrawlIntervalSection() {
  const queryClient = useQueryClient();
  const [localVal, setLocalVal] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);

  const { data: currentInterval, isLoading } = useQuery<number>({
    queryKey: ['crawl-interval'],
    queryFn: fetchCrawlInterval,
  });

  const initDone = localVal !== null;
  if (!initDone && currentInterval !== undefined) {
    setLocalVal(currentInterval);
  }

  const displayVal: number = localVal ?? currentInterval ?? 30;

  const mutation = useMutation({
    mutationFn: (m: number) => updateCrawlInterval(m),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crawl-interval'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  return (
    <Card className="border-border-standard bg-surface">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Timer className="w-4 h-4 text-brand" weight="fill" />
          크롤링 주기 설정
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <p className="text-xs text-text-muted leading-relaxed">
          인허가 변동 감지 주기를 설정합니다. 짧을수록 실시간에 가깝지만 API 호출 횟수가 늘어납니다.
          권장값: <span className="text-text-primary font-medium">30분</span>
        </p>

        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-bold text-text-primary tabular-nums">
            {isLoading ? '—' : displayVal}
          </span>
          <span className="text-sm text-text-muted">분마다 감지</span>
          {saved && (
            <span className="ml-2 text-xs text-brand flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" weight="fill" /> 저장됨
            </span>
          )}
        </div>

        <div className="space-y-2">
          <input
            id="crawl-interval-slider"
            type="range"
            min={5}
            max={120}
            step={5}
            value={displayVal}
            onChange={(e) => setLocalVal(Number(e.target.value))}
            className="w-full accent-brand cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-text-muted">
            <span>5분 (최소)</span>
            <span>120분 (최대)</span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {PRESET_MINUTES.map((m) => (
            <button
              key={m}
              onClick={() => setLocalVal(m)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${displayVal === m
                  ? 'bg-brand/15 border-brand/50 text-brand'
                  : 'bg-surface border-border-standard text-text-muted hover:text-text-primary hover:border-brand/30'
                }`}
            >
              {m}분
            </button>
          ))}
        </div>

        <button
          id="save-crawl-interval-btn"
          onClick={() => mutation.mutate(displayVal)}
          disabled={mutation.isPending || displayVal === currentInterval}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ArrowsClockwise className={`w-4 h-4 ${mutation.isPending ? 'animate-spin' : ''}`} />
          {mutation.isPending ? '적용 중...' : '주기 적용'}
        </button>

        <p className="text-[11px] text-text-muted">
          * 변경 즉시 서버에 반영됩니다. 서버 재시작 후에는 기본값(30분)으로 초기화됩니다.
        </p>
      </CardContent>
    </Card>
  );
}
