import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChartBar, Clock, Database, ArrowUpRight } from '@phosphor-icons/react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, Cell,
} from 'recharts';

import { fetchChngDtTrend } from '../api';
import type { ChngDtTrendResponse } from '../types';

// I2500 API total_count 추세를 Bar Chart로 시각화
// - 연두색 Bar: 당시 I2500 API가 반환한 총 레코드 수 (api_raw_total_count)
// - 주황색 Bar: 그 중 실제 신규 감지된 변경 건 (new_inserted)

export function ChngDtTrendSection() {
  const [viewDate, setViewDate] = useState<'today' | 'yesterday'>('today');

  const { data: trendData, isLoading } = useQuery<ChngDtTrendResponse>({
    queryKey: ['chngDtTrend'],
    queryFn: fetchChngDtTrend,
    staleTime: 5000,
    refetchInterval: 10000,
  });

  if (isLoading) {
    return (
      <div className="bg-surface border border-border-standard rounded-xl p-5 h-80 flex items-center justify-center">
        <div className="text-sm text-text-muted animate-pulse">트렌드 데이터 불러오는 중...</div>
      </div>
    );
  }

  const todayEntries = trendData?.today_entries ?? [];
  const yesterdayEntries = trendData?.yesterday_entries ?? [];
  const activeEntries = viewDate === 'today' ? todayEntries : yesterdayEntries;


  const formatDate = (dateStr?: string) => {
    if (!dateStr || dateStr.length !== 8) return dateStr ?? '';
    return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
  };

  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch {
      return isoString;
    }
  };

  // 최신 스냅샷의 I2500 전체 레코드 수 (api_raw_total_count 우선)
  const latestEntry = activeEntries.length > 0 ? activeEntries[activeEntries.length - 1] : null;
  const latestRawTotal = latestEntry
    ? ((latestEntry as any).api_raw_total_count ?? latestEntry.total_api_count)
    : 0;
  const totalInserted = activeEntries.reduce((s, e) => s + e.new_inserted, 0);
  const avgElapsed = activeEntries.length > 0
    ? (activeEntries.reduce((s, e) => s + e.elapsed_sec, 0) / activeEntries.length).toFixed(1)
    : '0';

  // 최근 24개 데이터 포인트만 표시 (과도한 바 방지)
  const chartData = activeEntries.slice(-24).map(e => ({
    time: formatTime(e.polled_at),
    'I2500 총 레코드': (e as any).api_raw_total_count ?? e.total_api_count,
    '신규 감지': e.new_inserted,
    elapsed: e.elapsed_sec,
  }));

  // api_raw_total_count가 0인지 확인 (이전 데이터)
  const hasRawTotal = activeEntries.some(e => (e as any).api_raw_total_count > 0);

  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
        <h2 className="flex items-center gap-2 text-base font-semibold text-text-primary">
          <ChartBar className="w-5 h-5 text-brand" weight="fill" />
          I2500 전략C — 실시간 CHNG_DT 추세
        </h2>

        {/* Toggle tabs */}
        <div className="flex rounded-lg bg-background p-0.5 border border-border-standard text-xs">
          <button
            onClick={() => setViewDate('today')}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              viewDate === 'today' ? 'bg-surface font-semibold text-brand shadow-sm' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            오늘 ({formatDate(trendData?.today_date)})
          </button>
          <button
            onClick={() => setViewDate('yesterday')}
            className={`px-3 py-1.5 rounded-md transition-colors ${
              viewDate === 'yesterday' ? 'bg-surface font-semibold text-brand shadow-sm' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            어제 ({formatDate(trendData?.yesterday_date)})
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
        {/* I2500 최신 총 레코드 수 */}
        <div className="p-4 rounded-xl border border-border-standard bg-background/50 flex items-center justify-between">
          <div>
            <div className="text-xs text-text-muted font-medium mb-1">I2500 API 최신 총 레코드 수</div>
            <div className="text-2xl font-bold text-[#3ecf8e] font-mono">
              {latestRawTotal.toLocaleString()}건
            </div>
            <div className="text-[10px] text-text-muted mt-0.5">
              {hasRawTotal ? '실시간 api total_count' : '수집 행 수 (api_raw_total_count 수집 전)'}
            </div>
          </div>
          <Database className="w-8 h-8 text-[#3ecf8e]/30" weight="fill" />
        </div>

        {/* 신규 변경 감지 누적 */}
        <div className="p-4 rounded-xl border border-border-standard bg-background/50 flex items-center justify-between">
          <div>
            <div className="text-xs text-text-muted font-medium mb-1">I2861 교차검증 신규 감지 (누적)</div>
            <div className="text-2xl font-bold text-orange-400 font-mono">
              {totalInserted.toLocaleString()}건
            </div>
            <div className="text-[10px] text-text-muted mt-0.5">I2861 LCNS_NO 검증 완료 후 INSERT</div>
          </div>
          <ArrowUpRight className="w-8 h-8 text-orange-400/30" weight="bold" />
        </div>

        {/* 평균 소요시간 */}
        <div className="p-4 rounded-xl border border-border-standard bg-background/50 flex items-center justify-between">
          <div>
            <div className="text-xs text-text-muted font-medium mb-1">평균 폴링 소요시간</div>
            <div className="text-2xl font-bold text-blue-400 font-mono">{avgElapsed}초</div>
            <div className="text-[10px] text-text-muted mt-0.5">전페이지 수집 기준</div>
          </div>
          <Clock className="w-8 h-8 text-blue-400/30" />
        </div>
      </div>

      {/* Bar Chart */}
      {chartData.length > 0 ? (
        <div className="space-y-4">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }} barGap={2}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)}
                  axisLine={false}
                  tickLine={false}
                  width={45}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  axisLine={false}
                  tickLine={false}
                  width={30}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--surface)',
                    border: '1px solid var(--border-standard)',
                    borderRadius: '10px',
                    fontSize: '12px',
                    boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
                  }}
                  labelStyle={{ color: 'var(--text-secondary)', fontWeight: 600, marginBottom: 4 }}
                  labelFormatter={(label) => `🕐 ${label}`}
                  formatter={(value: number, name: string) => [
                    `${value.toLocaleString()}건`,
                    name,
                  ]}
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                  iconType="square"
                />
                {/* 왼쪽 축: I2500 전체 레코드 수 */}
                <Bar
                  yAxisId="left"
                  dataKey="I2500 총 레코드"
                  fill="#3ecf8e"
                  opacity={0.85}
                  radius={[3, 3, 0, 0]}
                  maxBarSize={24}
                />
                {/* 오른쪽 축: 신규 감지 건수 */}
                <Bar
                  yAxisId="right"
                  dataKey="신규 감지"
                  fill="#f97316"
                  opacity={0.9}
                  radius={[3, 3, 0, 0]}
                  maxBarSize={24}
                >
                  {chartData.map((entry, idx) => (
                    <Cell
                      key={idx}
                      fill={entry['신규 감지'] > 0 ? '#f97316' : '#f9731640'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* 설명 */}
          <div className="flex items-start gap-2.5 px-4 py-3 rounded-lg border border-border-standard bg-background/30 text-text-secondary text-xs">
            <ChartBar className="w-4 h-4 mt-0.5 shrink-0 text-text-muted" />
            <p className="leading-relaxed">
              <span className="font-semibold text-[#3ecf8e]">녹색 바</span>는 각 폴링 시점의{' '}
              <code className="font-mono text-brand bg-brand/5 px-1 py-0.5 rounded">I2500</code>{' '}
              API가 반환한 <code className="font-mono">total_count</code> 실시간 추세입니다. 이 값이 상승하면
              새로운 CHNG_DT 레코드가 API에 추가됐음을 의미합니다.{' '}
              <span className="font-semibold text-orange-400">주황색 바</span>는 해당 주기에{' '}
              <code className="font-mono text-red-400 bg-red-400/5 px-1 py-0.5 rounded">I2861</code>{' '}
              단건 교차검증 후 실제로 DB에 삽입된 신규 변경 건입니다.
            </p>
          </div>
        </div>
      ) : (
        <div className="h-64 flex flex-col items-center justify-center border border-dashed border-border-standard rounded-xl gap-3">
          <Database className="w-8 h-8 text-text-muted/40" />
          <div className="text-sm text-text-muted">선택한 날짜의 수집 이력이 아직 없습니다.</div>
          <div className="text-xs text-text-muted/60">전략C 폴러가 실행되면 자동으로 차트가 채워집니다.</div>
        </div>
      )}
    </div>
  );
}
