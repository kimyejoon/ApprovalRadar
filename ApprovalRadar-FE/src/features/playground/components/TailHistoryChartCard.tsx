import { Broadcast } from '@phosphor-icons/react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { Card, SectionTitle } from './Shared';
import type { TailHistoryEntry } from '../types';

export function TailHistoryChartCard({ tailHistory }: { tailHistory: TailHistoryEntry[] }) {
  return (
    <Card>
      <SectionTitle icon={<Broadcast className="w-5 h-5 text-purple-400" />} title="일별 Known Tail 추이" />
      {tailHistory.length > 0 ? (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={tailHistory} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis
                dataKey="record_date"
                tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis
                tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
                domain={['dataMin - 1000', 'dataMax + 1000']}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--surface)',
                  border: '1px solid var(--border-standard)',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                labelStyle={{ color: 'var(--text-secondary)' }}
                formatter={(value: number) => [`${value.toLocaleString()}건`, 'Total Count']}
                labelFormatter={(label: string) => `날짜: ${label}`}
              />
              <Bar dataKey="total_count" radius={[4, 4, 0, 0]}>
                {tailHistory.map((_, index) => (
                  <Cell
                    key={index}
                    fill={index === tailHistory.length - 1 ? '#3ecf8e' : 'rgba(62, 207, 142, 0.3)'}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-64 flex items-center justify-center text-sm text-text-muted">
          데이터 수집 중... (Tail Ping 실행 후 표시됩니다)
        </div>
      )}
    </Card>
  );
}
