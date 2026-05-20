import { ArrowClockwise } from '@phosphor-icons/react';
import type { SchedulerStatus } from '../types';

interface SchedulerSectionProps {
  scheduler: SchedulerStatus | null;
}

function formatRemaining(sec: number | null): string {
  if (sec === null || sec < 0) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function SchedulerSection({ scheduler }: SchedulerSectionProps) {
  return (
    <div className="bg-surface border border-border-standard rounded-xl p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
        <ArrowClockwise className="w-5 h-5 text-brand" />
        스케줄러 상태
      </h2>
      {scheduler ? (
        <div className="space-y-2">
          <p className="text-xs text-text-muted mb-3">현재 시각: {scheduler.current_time}</p>
          <div className="space-y-1.5">
            {scheduler.jobs.map((job) => (
              <div
                key={job.job_id}
                className="flex items-center justify-between px-3 py-2 rounded-lg bg-background text-sm"
              >
                <span className="text-text-secondary truncate max-w-[60%]">{job.name}</span>
                <div className="flex items-center gap-3">
                  {job.next_run && (
                    <span className="text-xs text-text-muted">{job.next_run}</span>
                  )}
                  <span className={`font-mono text-xs px-2 py-0.5 rounded ${
                    job.seconds_remaining !== null && job.seconds_remaining < 60
                      ? 'bg-brand/15 text-brand font-semibold'
                      : 'bg-border-subtle text-text-muted'
                  }`}>
                    {formatRemaining(job.seconds_remaining)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-sm text-text-muted">로딩 중...</div>
      )}
    </div>
  );
}
