import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { fetchIndicators } from '@/lib/api';
import { useIndicatorStore } from '@/store/useIndicatorStore';

export function DashboardIndicators() {
  const setTodayNewCount = useIndicatorStore(state => state.setTodayNewCount);

  const { data: indicatorResponse } = useQuery({
    queryKey: ['indicators'],
    queryFn: () => fetchIndicators({}),
    refetchInterval: 1000 * 60 * 5, // 5 min polling
    refetchOnWindowFocus: true,
  });

  const data = indicatorResponse?.data;

  useEffect(() => {
    if (data?.total_approvals !== undefined) {
      setTodayNewCount(data.total_approvals);
    }
  }, [data?.total_approvals, setTodayNewCount]);

  const todayChangesCount = data?.total_approvals || 0;

  // 신규 인허가 비율 (Pie Chart)
  const pieData = useMemo(() => {
    if (!data?.status_distribution) return [];
    return data.status_distribution.map(d => ({
      name: d.name,
      value: d.value,
      color: d.name.includes('정상') || d.name.includes('영업') ? '#3ecf8e' : '#f87171'
    }));
  }, [data]);

  // 트렌드 차트 데이터 (Bar Chart)
  const barData = useMemo(() => {
    if (!data?.trend_chart) return [];
    // 최근 7일 데이터만 가져오기
    const recent7DaysData = data.trend_chart.slice(-7);
    return recent7DaysData.map(item => {
      let formattedDate = item.date;
      if (item.date && item.date.length === 8 && !item.date.includes('-')) {
        const month = parseInt(item.date.substring(4, 6), 10);
        const day = parseInt(item.date.substring(6, 8), 10);
        formattedDate = `${month}월 ${day}일`;
      } else if (item.date && item.date.includes('-')) {
        const parts = item.date.split('-');
        if (parts.length === 3) {
          formattedDate = `${parseInt(parts[1], 10)}월 ${parseInt(parts[2], 10)}일`;
        }
      }
      return {
        ...item,
        date: formattedDate
      };
    });
  }, [data]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6">
      {/* Indicator Card */}
      <Card className="flex flex-col justify-center border-border-standard shadow-sm bg-surface-primary">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-text-muted">금일 인허가 변동 건수</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-4xl font-bold text-text-primary">{todayChangesCount.toLocaleString()}건</div>
        </CardContent>
      </Card>

      {/* Pie Chart: 신규 인허가 비율 */}
      <Card className="border-border-standard shadow-sm bg-surface-primary">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-text-muted">상태별 변동 비율</CardTitle>
        </CardHeader>
        <CardContent className="h-[140px] flex items-center justify-center pb-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={35}
                outerRadius={55}
                paddingAngle={2}
                dataKey="value"
                stroke="none"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => [`${value}건`, '']}
                contentStyle={{ borderRadius: '8px', border: '1px solid var(--color-border-standard)', backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)', fontSize: '12px' }}
                itemStyle={{ color: 'var(--color-text-primary)' }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-col w-32 justify-center space-y-1 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-brand"></span>
              <span className="text-text-secondary">신규/영업</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-400"></span>
              <span className="text-text-secondary">폐업/취소</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Bar Chart: 주간 트렌드 */}
      <Card className="border-border-standard shadow-sm bg-surface-primary lg:col-span-2">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-text-muted">최근 7일 변동 추이</CardTitle>
        </CardHeader>
        <CardContent className="h-[140px] pb-0">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-subtle)" />
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
                dy={5}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
              />
              <Tooltip
                cursor={{ fill: 'var(--color-accent)' }}
                contentStyle={{ borderRadius: '8px', border: '1px solid var(--color-border-standard)', backgroundColor: 'var(--color-surface)', color: 'var(--color-text-primary)', fontSize: '12px' }}
                itemStyle={{ color: 'var(--color-text-primary)' }}
              />
              <Bar dataKey="count" fill="var(--color-brand)" radius={[4, 4, 0, 0]} maxBarSize={30} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
