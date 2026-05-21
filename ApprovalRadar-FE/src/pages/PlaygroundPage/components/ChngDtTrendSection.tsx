import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChartLineUp, Clock, Calendar, Info } from '@phosphor-icons/react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts';

import { fetchChngDtTrend } from '../api';
import type { ChngDtTrendResponse, ChngDtPollEntry } from '../types';

export function ChngDtTrendSection() {
  const [viewDate, setViewDate] = useState<'today' | 'yesterday'>('today');

  const { data: trendData, isLoading } = useQuery<ChngDtTrendResponse>({
    queryKey: ['chngDtTrend'],
    queryFn: fetchChngDtTrend,
    staleTime: 5000,
    refetchInterval: 10000, // 10초마다 자동 갱신
  });

  if (isLoading) {
    return (
      <div className="bg-surface border border-border-standard rounded-xl p-5 h-80 flex items-center justify-center">
        <div className="text-sm text-text-muted">트렌드 데이터 불러오는 중...</div>
      </div>
    );
  }

  const todayEntries = trendData?.today_entries ?? [];
  const yesterdayEntries = trendData?.yesterday_entries ?? [];
  const activeEntries = viewDate === 'today' ? todayEntries : yesterdayEntries;
  const targetDateStr = viewDate === 'today' ? trendData?.today_date : trendData?.yesterday_date;

  // 날짜 포맷 (YYYYMMDD -> YYYY-MM-DD)
  const formatDate = (dateStr?: string) => {
    if (!dateStr || dateStr.length !== 8) return dateStr ?? '';
    return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
  };

  // 시간 포맷 (ISO -> HH:MM)
  const formatTime = (isoString: string) => {
    try {
      const date = new Date(isoString);
      const hh = String(date.getHours()).padStart(2, '0');
      const mm = String(date.getMinutes()).padStart(2, '0');
      return `${hh}:${mm}`;
    } catch {
      return isoString;
    }
  };

  // 현재 데이터셋 요약 계산
  const currentSyncTotal = activeEntries.length > 0 ? activeEntries[activeEntries.length - 1].total_api_count : 0;
  const currentInsertedTotal = activeEntries.reduce((sum, e) => sum + e.new_inserted, 0);
  const currentAvgElapsed = activeEntries.length > 0 ? (activeEntries.reduce((sum, e) => sum + e.elapsed_sec, 0) / activeEntries.length).toFixed(1) : '0';

  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
        <h2 className="flex items-center gap-2 text-base font-semibold text-text-primary">
          <ChartLineUp className="w-5 h-5 text-brand" />
          I2500 시간대별 동기화 & 실시간 변경 감지 트렌드
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
        <div className="p-4 rounded-xl border border-border-standard bg-background/50 flex items-center justify-between">
          <div>
            <div className="text-xs text-text-muted font-medium mb-1">최종 API 동기화 대상 (누적)</div>
            <div className="text-2xl font-bold text-text-primary font-mono">{currentSyncTotal.toLocaleString()}건</div>
          </div>
          <Calendar className="w-8 h-8 text-text-muted/40" />
        </div>
        <div className="p-4 rounded-xl border border-border-standard bg-background/50 flex items-center justify-between">
          <div>
            <div className="text-xs text-text-muted font-medium mb-1">진짜 실시간 변경 감지 (누적)</div>
            <div className="text-2xl font-bold text-brand font-mono">{currentInsertedTotal.toLocaleString()}건</div>
          </div>
          <ChartLineUp className="w-8 h-8 text-brand/30" />
        </div>
        <div className="p-4 rounded-xl border border-border-standard bg-background/50 flex items-center justify-between">
          <div>
            <div className="text-xs text-text-muted font-medium mb-1">평균 API 호출 소요시간</div>
            <div className="text-2xl font-bold text-blue-400 font-mono">{currentAvgElapsed}초</div>
          </div>
          <Clock className="w-8 h-8 text-blue-500/30" />
        </div>
      </div>

      {/* Chart container */}
      {activeEntries.length > 0 ? (
        <div className="space-y-6">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={activeEntries} margin={{ top: 10, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis
                  dataKey="polled_at"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  tickFormatter={formatTime}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`}
                  label={{ value: 'API 동기화 대상 (건)', angle: -90, position: 'insideLeft', offset: -5, style: { fontSize: 10, fill: 'var(--text-muted)' } }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  label={{ value: '변경 감지 (건)', angle: 90, position: 'insideRight', offset: 0, style: { fontSize: 10, fill: 'var(--text-muted)' } }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--surface)',
                    border: '1px solid var(--border-standard)',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                  labelStyle={{ color: 'var(--text-secondary)' }}
                  labelFormatter={(label: string) => `동기화 시각: ${new Date(label).toLocaleTimeString()}`}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="total_api_count"
                  name="API 동기화 (I2500)"
                  stroke="#3ecf8e"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="new_inserted"
                  name="변경 감지 (I2861 검증 완료)"
                  stroke="#ef4444"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          
          <div className="flex items-start gap-2.5 px-4 py-3 rounded-lg border border-border-standard bg-background/30 text-text-secondary text-xs">
            <Info className="w-4 h-4 mt-0.5 shrink-0 text-text-muted" />
            <p className="leading-relaxed">
              **트렌드 분석 안내:** 연한 녹색선은 식품안전나라 <code className="font-mono text-brand bg-brand/5 px-1 py-0.5 rounded">I2500</code> 오늘 자 동기화 레코드 총합 추이이며, 빨간색 선은 동기화 후보들 중 <code className="font-mono text-red-400 bg-red-400/5 px-1 py-0.5 rounded">I2861</code> 단건 조회를 통해 **실제 오늘 변동이 확인된 진짜 변경건** 누적 감지선입니다. 19시 이전에는 어제 날짜 쿼리를 통해 우회 수집하므로 두 값 모두 점진적 우상향 곡선을 그립니다.
            </p>
          </div>
        </div>
      ) : (
        <div className="h-64 flex items-center justify-center border border-dashed border-border-standard rounded-xl text-sm text-text-muted">
          선택한 날짜의 수집 이력이 존재하지 않습니다.
        </div>
      )}
    </div>
  );
}
