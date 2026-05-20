export function UsageBar({ used, limit = 1000 }: { used: number; limit?: number }) {
  const pct = Math.min((used / limit) * 100, 100);
  const color = pct >= 90 ? 'bg-red-500' : pct >= 60 ? 'bg-yellow-400' : 'bg-brand';
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="flex-1 h-1.5 rounded-full bg-surface-secondary overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-text-muted font-mono whitespace-nowrap">
        {used.toLocaleString()} / {limit.toLocaleString()}
      </span>
    </div>
  );
}
