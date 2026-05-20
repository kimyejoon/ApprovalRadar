import { useState, useEffect, useCallback } from 'react';
import { ArrowClockwise, Play, Broadcast, MagnifyingGlass, Lightning, ClockCounterClockwise } from '@phosphor-icons/react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { API_BASE_URL } from '@/lib/api';

// ─── Types ──────────────────────────────────────────────────────────────────

interface JobStatus {
  job_id: string;
  name: string;
  next_run: string | null;
  seconds_remaining: number | null;
  is_running: boolean;
}

interface SchedulerStatus {
  jobs: JobStatus[];
  current_time: string;
}

interface TodayDetection {
  today_date: string;
  today_count: number;
  yesterday_date: string;
  yesterday_count: number;
  total_records: number;
  scan_coverage_pct: number;
  recent_detections: {
    business_name: string;
    license_no: string;
    industry_type: string;
    event_date: string;
    updated_at: string;
    update_type: string;
  }[];
}

interface TailHistoryEntry {
  record_date: string;
  total_count: number;
}

interface PageScanEntry {
  page_number: number;
  page_start: number;
  fingerprint: string | null;
  last_scanned: string | null;
}

interface SmartSweepLogEntry {
  run_at: string;
  strategy: string;
  probe_calls: number;
  hot_segs: number;
  collected: number;
  elapsed_sec: number;
  detail: { seg: string; class: string; first_chng: string }[];
}

interface SmartSweepCache {
  total_cached: number;
  hot: number;
  warm: number;
  cold: number;
  segments: { seg: string; total_count: number; first_chng: string; cls: string; probed_at: string }[];
}


// ─── API Helpers ────────────────────────────────────────────────────────────

const BASE = `${API_BASE_URL}/api/v1/playground`;

async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  const res = await fetch(`${BASE}/scheduler-status`);
  if (!res.ok) throw new Error('Failed');
  return res.json();
}

async function triggerJob(jobType: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/trigger/${jobType}`, { method: 'POST' });
  return res.json();
}

async function triggerRangeScan(start: number, end: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/trigger/range-scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end }),
  });
  return res.json();
}

async function fetchTodayDetection(): Promise<TodayDetection> {
  const res = await fetch(`${BASE}/today-detection/I2861`);
  if (!res.ok) throw new Error('Failed');
  return res.json();
}

async function fetchTailHistory(): Promise<TailHistoryEntry[]> {
  const res = await fetch(`${BASE}/tail-history/I2861`);
  if (!res.ok) throw new Error('Failed');
  const data = await res.json();
  return data.entries;
}

async function fetchPageScanHistory(): Promise<{ total_pages: number; scanned_pages: number; entries: PageScanEntry[] }> {
  const res = await fetch(`${BASE}/page-scan-history/I2861`);
  if (!res.ok) throw new Error('Failed');
  return res.json();
}

async function fetchSmartSweepStatus(): Promise<{ entries: SmartSweepLogEntry[]; count: number }> {
  const res = await fetch(`${BASE}/smart-sweep/status`);
  if (!res.ok) return { entries: [], count: 0 };
  return res.json();
}

async function fetchSmartSweepCache(): Promise<SmartSweepCache> {
  const res = await fetch(`${BASE}/smart-sweep/cache`);
  if (!res.ok) return { total_cached: 0, hot: 0, warm: 0, cold: 0, segments: [] };
  return res.json();
}


// ─── Helper Components ──────────────────────────────────────────────────────

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-surface border border-border-standard rounded-xl p-5 ${className}`}>
      {children}
    </div>
  );
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
      {icon}
      {title}
    </h2>
  );
}

function formatRemaining(sec: number | null): string {
  if (sec === null || sec < 0) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export function PlaygroundPage() {
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [today, setToday] = useState<TodayDetection | null>(null);
  const [tailHistory, setTailHistory] = useState<TailHistoryEntry[]>([]);
  const [pageScan, setPageScan] = useState<{ total_pages: number; scanned_pages: number; entries: PageScanEntry[] } | null>(null);
  const [sweepLog, setSweepLog] = useState<SmartSweepLogEntry[]>([]);
  const [sweepCache, setSweepCache] = useState<SmartSweepCache | null>(null);

  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [rangeStart, setRangeStart] = useState<string>('1');
  const [rangeEnd, setRangeEnd] = useState<string>('10000');

  const refresh = useCallback(async () => {
    try {
      const [sched, det, tail, pages, swLog, swCache] = await Promise.all([
        fetchSchedulerStatus(),
        fetchTodayDetection(),
        fetchTailHistory(),
        fetchPageScanHistory(),
        fetchSmartSweepStatus(),
        fetchSmartSweepCache(),
      ]);
      setScheduler(sched);
      setToday(det);
      setTailHistory(tail);
      setPageScan(pages);
      setSweepLog(swLog.entries);
      setSweepCache(swCache);
    } catch (e) {
      console.error('Playground refresh failed:', e);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000); // 10초 자동 갱신
    return () => clearInterval(timer);
  }, [refresh]);

  const handleTrigger = async (jobType: string) => {
    setLoading(true);
    setTriggerMsg(null);
    try {
      const result = await triggerJob(jobType);
      setTriggerMsg(result.message);
      setTimeout(() => setTriggerMsg(null), 5000);
    } catch {
      setTriggerMsg('트리거 실패');
    } finally {
      setLoading(false);
    }
  };

  const handleRangeScan = async () => {
    const s = parseInt(rangeStart, 10);
    const e = parseInt(rangeEnd, 10);
    if (isNaN(s) || isNaN(e) || s < 1 || e < s) {
      setTriggerMsg('잘못된 범위입니다');
      setTimeout(() => setTriggerMsg(null), 3000);
      return;
    }
    setLoading(true);
    setTriggerMsg(null);
    try {
      const result = await triggerRangeScan(s, e);
      setTriggerMsg(result.message);
      setTimeout(() => setTriggerMsg(null), 5000);
    } catch {
      setTriggerMsg('Range Scan 트리거 실패');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">크롤러 플레이그라운드</h1>
          <p className="text-sm text-text-muted mt-0.5">실시간 크롤러 모니터링 및 수동 제어</p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg border border-border-standard hover:bg-surface transition-colors text-text-secondary"
        >
          <ArrowClockwise className="w-4 h-4" />
          새로고침
        </button>
      </div>

      {/* Toast */}
      {triggerMsg && (
        <div className="fixed top-4 right-4 z-50 bg-brand text-white px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium animate-in slide-in-from-top-2">
          {triggerMsg}
        </div>
      )}

      {/* Row 1: Scheduler + Triggers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Scheduler Status */}
        <Card>
          <SectionTitle icon={<ArrowClockwise className="w-5 h-5 text-brand" />} title="스케줄러 상태" />
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
        </Card>

        {/* Trigger Buttons */}
        <Card>
          <SectionTitle icon={<Lightning className="w-5 h-5 text-yellow-500" />} title="수동 트리거" />
          <p className="text-xs text-text-muted mb-4">사이클 사이 Term에서 즉시 실행합니다.</p>
          <div className="grid grid-cols-2 gap-3">
            {/* Oldest-First Scan — 연식 1h↑ 우선 전수 스캔 (핵심 버튼) */}
            <button
              onClick={() => handleTrigger('oldest_first_scan')}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-green-500/30 bg-green-500/5 hover:bg-green-500/10 transition-all text-sm font-medium text-green-400 disabled:opacity-50 col-span-2"
            >
              <ClockCounterClockwise className="w-4 h-4" />
              Oldest-First Scan <span className="text-xs text-text-muted ml-1">(연식 1h↑ 페이지 전수 스캔)</span>
            </button>
            <button
              onClick={() => handleTrigger('tail_ping')}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-border-standard bg-background hover:bg-surface transition-all text-sm font-medium text-text-primary disabled:opacity-50"
            >
              <Broadcast className="w-4 h-4 text-purple-400" />
              Tail Ping
            </button>
            <button
              onClick={() => handleTrigger('scraper')}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-border-standard bg-background hover:bg-surface transition-all text-sm font-medium text-text-primary disabled:opacity-50"
            >
              <MagnifyingGlass className="w-4 h-4 text-orange-400" />
              Scraper
            </button>
          </div>

          {/* Range Scan */}
          <div className="mt-4 pt-4 border-t border-border-subtle">
            <p className="text-xs font-medium text-text-secondary mb-2">🎯 범위 지정 스캔</p>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={rangeStart}
                onChange={(e) => setRangeStart(e.target.value)}
                placeholder="시작"
                className="w-28 px-3 py-2 rounded-lg border border-border-standard bg-background text-sm text-text-primary text-right font-mono focus:outline-none focus:ring-1 focus:ring-brand"
              />
              <span className="text-text-muted text-sm">~</span>
              <input
                type="number"
                value={rangeEnd}
                onChange={(e) => setRangeEnd(e.target.value)}
                placeholder="종료"
                className="w-28 px-3 py-2 rounded-lg border border-border-standard bg-background text-sm text-text-primary text-right font-mono focus:outline-none focus:ring-1 focus:ring-brand"
              />
              <button
                onClick={handleRangeScan}
                disabled={loading}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-orange-400/30 bg-orange-400/5 hover:bg-orange-400/10 transition-all text-sm font-medium text-orange-500 disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" />
                스캔
              </button>
            </div>
            <p className="text-[10px] text-text-muted mt-1.5">
              레코드 번호 범위 (1~952,999). 예: 940001~952999 = 마지막 13p
            </p>
          </div>
        </Card>
      </div>

      {/* Row 2: Today Detection + Tail History Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Today Detection */}
        <Card>
          <SectionTitle icon={<Play className="w-5 h-5 text-red-400" />} title="오늘 감지 현황" />
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
        </Card>

        {/* Tail History Bar Chart */}
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
      </div>



      {/* Row 3: Page Scan History */}
      <Card>
        <SectionTitle icon={<MagnifyingGlass className="w-5 h-5 text-orange-400" />} title="페이지 스캔 히스토리" />
        {pageScan ? (
          <div>
            <div className="flex items-center gap-4 mb-4">
              <span className="text-sm text-text-secondary">
                전체 {pageScan.total_pages}p 중 <span className="text-brand font-semibold">{pageScan.scanned_pages}p</span> 스캔 완료
              </span>
              <div className="flex-1 h-2 bg-border-subtle rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand rounded-full transition-all"
                  style={{ width: `${pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100) : 0}%` }}
                />
              </div>
              <span className="text-sm text-text-muted font-mono">
                {pageScan.total_pages > 0 ? (pageScan.scanned_pages / pageScan.total_pages * 100).toFixed(1) : 0}%
              </span>
            </div>

            {/* Heatmap-style page grid */}
            <div className="flex flex-wrap gap-[2px]">
              {(() => {
                const nowMs = Date.now();
                const ONE_HOUR_MS = 60 * 60 * 1000;
                const todayStr = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

                return pageScan.entries.map((e) => {
                  const hasTime = !!e.last_scanned;
                  const hasFP = !!e.fingerprint;

                  let colorClass: string;
                  if (!hasFP) {
                    // 미스캔: 회색
                    colorClass = 'bg-border-subtle hover:bg-border-standard';
                  } else if (!hasTime) {
                    // FP만 있고 스캔 시각 없음 → 오늘 이전 취급: 회색
                    colorClass = 'bg-zinc-600/50 hover:bg-zinc-500/60';
                  } else {
                    // 스캔 시각 파싱
                    const scannedDate = e.last_scanned!.slice(0, 10); // YYYY-MM-DD
                    const scannedMs = new Date(e.last_scanned!).getTime();
                    const ageMs = nowMs - scannedMs;

                    if (scannedDate < todayStr) {
                      // 오늘 이전 스캔: 회색
                      colorClass = 'bg-zinc-600/50 hover:bg-zinc-500/60';
                    } else if (ageMs < ONE_HOUR_MS) {
                      // 1h 미만: 진한 초록
                      colorClass = 'bg-emerald-500 hover:bg-emerald-400';
                    } else {
                      // 1h 이상: 연한 초록
                      colorClass = 'bg-emerald-800/70 hover:bg-emerald-700/80';
                    }
                  }

                  return (
                    <div
                      key={e.page_number}
                      className={`w-3 h-3 rounded-[2px] transition-colors cursor-pointer ${colorClass}`}
                      title={`P${e.page_number} (${e.page_start.toLocaleString()}~)\n${hasFP ? `FP: ${e.fingerprint}` : '미스캔'}${hasTime ? `\n최종 스캔: ${e.last_scanned}` : ''}`}
                    />
                  );
                });
              })()}
            </div>
            <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-[2px] bg-emerald-500" />
                오늘 스캔 (1h 미만)
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-[2px] bg-emerald-800/70" />
                오늘 스캔 (1h 이상)
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-[2px] bg-zinc-600/50" />
                오늘 이전 스캔
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-[2px] bg-border-subtle" />
                미스캔
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-text-muted">로딩 중...</div>
        )}
      </Card>

      {/* SmartSweep 모니터 카드 */}
      <Card>
        <SectionTitle icon={<MagnifyingGlass size={18} className="text-violet-400" />} title="🔬 SmartSweep 실험 모니터" />
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => handleTrigger('smart_sweep_micro')}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 text-xs font-medium transition-colors border border-violet-600/30 disabled:opacity-40"
          >
            <Lightning size={13} /> Micro Probe (10탐침)
          </button>
          <button
            onClick={() => handleTrigger('smart_sweep_full')}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-xs font-medium transition-colors border border-indigo-600/30 disabled:opacity-40"
          >
            <ArrowClockwise size={13} /> Full Sweep (200seg)
          </button>
        </div>

        {/* 캐시 요약 */}
        {sweepCache && sweepCache.total_cached > 0 && (
          <div className="flex gap-3 mb-4">
            {[
              { label: '탐침 세그먼트', val: sweepCache.total_cached, color: 'text-zinc-300' },
              { label: '🎯 HOT', val: sweepCache.hot, color: 'text-red-400' },
              { label: '📅 WARM', val: sweepCache.warm, color: 'text-amber-400' },
              { label: '❄️ COLD', val: sweepCache.cold, color: 'text-zinc-500' },
            ].map(({ label, val, color }) => (
              <div key={label} className="bg-surface-2 rounded-lg px-3 py-2 text-center min-w-[70px]">
                <div className={`text-lg font-bold ${color}`}>{val}</div>
                <div className="text-[10px] text-text-muted mt-0.5">{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* 실행 이력 */}
        {sweepLog.length > 0 ? (
          <div className="space-y-2">
            <div className="text-xs text-text-muted mb-2">최근 {sweepLog.length}회 실행 이력</div>
            {sweepLog.slice(0, 5).map((entry, idx) => (
              <div key={idx} className="bg-surface-2 rounded-lg px-3 py-2.5 flex items-center gap-4 text-xs">
                <span className="text-text-muted shrink-0 w-[72px]">
                  {entry.run_at.slice(11, 19)}
                </span>
                <span className="text-zinc-400 w-[90px] shrink-0">{entry.strategy}</span>
                <span className="text-violet-300">탐침 {entry.probe_calls}회</span>
                <span className={entry.hot_segs > 0 ? 'text-red-400 font-semibold' : 'text-zinc-500'}>
                  HOT {entry.hot_segs}
                </span>
                <span className={entry.collected > 0 ? 'text-emerald-400 font-semibold' : 'text-zinc-600'}>
                  수집 {entry.collected}건
                </span>
                <span className="text-zinc-600 ml-auto">{entry.elapsed_sec.toFixed(1)}초</span>
              </div>
            ))}
            {sweepLog[0]?.detail.length > 0 && (
              <div className="mt-3 p-2 bg-surface-2 rounded-lg">
                <div className="text-xs text-text-muted mb-1.5">최근 실행 주목 세그먼트</div>
                {sweepLog[0].detail.map((d, i) => (
                  <div key={i} className="flex gap-2 text-xs py-0.5">
                    <span className={d.class === 'HOT' ? 'text-red-400' : 'text-zinc-500'}>
                      {d.class === 'HOT' ? '🎯' : '📅'} {d.seg}
                    </span>
                    <span className="text-zinc-500">first={d.first_chng}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-text-muted">아직 실행 이력 없음 — Micro Probe를 실행해보세요</div>
        )}
      </Card>
    </div>
  );
}
