import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Gauge, CheckCircle, ArrowsClockwise } from '@phosphor-icons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchRollingScanRate, updateRollingScanRate, fetchApiKeys } from '@/lib/api';

const SCAN_PRESETS = [30, 50, 80, 100, 150] as const;
const API_DAILY_LIMIT_PER_KEY = 1000;
const ESTIMATED_TOTAL_PAGES = 1198;

export function RollingScanSection() {
  const queryClient = useQueryClient();
  const [localVal, setLocalVal] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);

  const { data: currentRate, isLoading } = useQuery<number>({
    queryKey: ['rolling-scan-rate'],
    queryFn: fetchRollingScanRate,
  });

  const { data: keysData } = useQuery({
    queryKey: ['settings-api-keys'],
    queryFn: fetchApiKeys,
  });

  const initDone = localVal !== null;
  if (!initDone && currentRate !== undefined) {
    setLocalVal(currentRate);
  }

  const displayVal: number = localVal ?? currentRate ?? 100;

  const activeKeys = keysData?.keys.filter((k) => k.is_active && !k.is_exhausted).length ?? 2;
  const dailyApiLimit = activeKeys * API_DAILY_LIMIT_PER_KEY;

  const mutation = useMutation({
    mutationFn: (p: number) => updateRollingScanRate(p),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rolling-scan-rate'] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    },
  });

  return (
    <Card className="border-border-standard bg-surface">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-medium flex items-center gap-2">
          <Gauge className="w-4 h-4 text-brand" weight="fill" />
          Rolling Scan 설정
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <p className="text-xs text-text-muted leading-relaxed">
          매 크롤링 주기마다 스캔할 API 페이지 수를 설정합니다. 높을수록 변동 감지가 빨라지지만 API 호출량이 증가합니다.
        </p>

        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-bold text-text-primary tabular-nums">
            {isLoading ? '—' : displayVal}
          </span>
          <span className="text-sm text-text-muted">페이지/주기</span>
          {saved && (
            <span className="ml-2 text-xs text-brand flex items-center gap-1">
              <CheckCircle className="w-3.5 h-3.5" weight="fill" /> 저장됨
            </span>
          )}
        </div>

        <div className="space-y-2">
          <input
            id="rolling-scan-slider"
            type="range"
            min={10}
            max={200}
            step={10}
            value={displayVal}
            onChange={(e) => setLocalVal(Number(e.target.value))}
            className="w-full accent-brand cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-text-muted">
            <span>10 (안전)</span>
            <span>200 (최대)</span>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {SCAN_PRESETS.map((p) => (
            <button
              key={p}
              onClick={() => setLocalVal(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${displayVal === p
                  ? 'bg-brand/15 border-brand/50 text-brand'
                  : 'bg-surface border-border-standard text-text-muted hover:text-text-primary hover:border-brand/30'
                }`}
            >
              {p}페이지
            </button>
          ))}
        </div>

        <button
          id="save-rolling-scan-btn"
          onClick={() => mutation.mutate(displayVal)}
          disabled={mutation.isPending || displayVal === currentRate}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ArrowsClockwise className={`w-4 h-4 ${mutation.isPending ? 'animate-spin' : ''}`} />
          {mutation.isPending ? '적용 중...' : '스캔 속도 적용'}
        </button>

        <p className="text-[11px] text-text-muted">
          * 전체 페이지 수 약 {ESTIMATED_TOTAL_PAGES.toLocaleString()}개 기준. 활성 키 {activeKeys}개 × {API_DAILY_LIMIT_PER_KEY.toLocaleString()}회 = 일일 한도 {dailyApiLimit.toLocaleString()}회.
        </p>
      </CardContent>
    </Card>
  );
}
