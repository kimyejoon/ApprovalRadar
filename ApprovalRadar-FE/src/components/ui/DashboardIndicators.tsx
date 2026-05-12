import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { ApprovalMappedItem } from '@/lib/api';

interface DashboardIndicatorsProps {
  data: ApprovalMappedItem[];
}

export function DashboardIndicators({ data }: DashboardIndicatorsProps) {
  const todayChangesCount = data.length;

  // 신규 인허가 비율 (Pie Chart)
  const pieData = useMemo(() => {
    const newCount = data.filter(d => d.status.includes('정상') || d.status.includes('영업')).length || 1;
    const closedCount = data.filter(d => d.status.includes('폐업') || d.status.includes('취소')).length || 0;

    return [
      { name: '신규/영업', value: newCount, color: '#3ecf8e' },
      { name: '폐업/취소', value: closedCount, color: '#f87171' }
    ];
  }, [data]);

  // 트렌드 차트 데이터 (Bar Chart - 하드코딩 유지하되 추후 API 연동 용이하도록 구조화)
  const barData = useMemo(() => {
    return [
      { date: '5.05', count: 12 },
      { date: '5.06', count: 8 },
      { date: '5.07', count: 15 },
      { date: '5.08', count: 10 },
      { date: '5.09', count: 22 },
      { date: '5.10', count: 18 },
      { date: '5.11', count: 9 }, // 오늘
    ];
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-6">
      {/* Indicator Card */}
      <Card className="flex flex-col justify-center border-border-standard shadow-sm bg-surface-primary">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-text-muted">금일 인허가 변동 건수</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-4xl font-bold text-text-primary">{todayChangesCount}건</div>
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
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px' }}
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
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 10, fill: '#64748b' }}
                dy={5}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 10, fill: '#64748b' }}
              />
              <Tooltip
                cursor={{ fill: '#f8fafc' }}
                contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', fontSize: '12px' }}
              />
              <Bar dataKey="count" fill="#3ecf8e" radius={[4, 4, 0, 0]} maxBarSize={30} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}
