import { useState, useEffect, useCallback } from 'react';
import { ArrowClockwise, Play, RocketLaunch, Broadcast, MagnifyingGlass, Lightning, ChartLine } from '@phosphor-icons/react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
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

interface ChngDtPollEntry {
  polled_at: string;
  total_api_count: number;
  new_inserted: number;
  already_exists: number;
  pages_fetched: number;
  elapsed_sec: number;
}

interface ChngDtTrend {
  target_date: string;
  entries: ChngDtPollEntry[];
  latest_total: number;
  total_inserted: number;
  yesterday_date: string;
  yesterday_entries: ChngDtPollEntry[];
  today_date: string;
  today_entries: ChngDtPollEntry[];
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

async function fetchChngDtTrend(): Promise<ChngDtTrend> {
  const res = await fetch(`${BASE}/chng-dt-trend`);
  if (!res.ok) throw new Error('Failed');
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
  const [chngDtTrend, setChngDtTrend] = useState<ChngDtTrend | null>(null);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [rangeStart, setRangeStart] = useState<string>('1');
  const [rangeEnd, setRangeEnd] = useState<string>('10000');

  const refresh = useCallback(async () => {
    try {
      const [sched, det, tail, pages, trend] = await Promise.all([
        fetchSchedulerStatus(),
        fetchTodayDetection(),
        fetchTailHistory(),
        fetchPageScanHistory(),
        fetchChngDtTrend(),
      ]);
      setScheduler(sched);
      setToday(det);
      setTailHistory(tail);
      setPageScan(pages);
      setChngDtTrend(trend);
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
            <button
              onClick={() => handleTrigger('rolling_scan')}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-border-standard bg-background hover:bg-surface transition-all text-sm font-medium text-text-primary disabled:opacity-50"
            >
              <ArrowClockwise className="w-4 h-4 text-blue-400" />
              Rolling Scan
            </button>
            <button
              onClick={() => handleTrigger('boost_scan')}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-brand/30 bg-brand/5 hover:bg-brand/10 transition-all text-sm font-medium text-brand disabled:opacity-50"
            >
              <RocketLaunch className="w-4 h-4" />
              Boost Scan
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
            <button
              onClick={() => handleTrigger('chng_dt_poll')}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-emerald-400/30 bg-emerald-400/5 hover:bg-emerald-400/10 transition-all text-sm font-medium text-emerald-500 disabled:opacity-50 col-span-2"
            >
              📡 I2500 CHNG_DT Poller
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

      {/* Row 2.5: CHNG_DT Poller Trend */}
      <Card>
        <SectionTitle icon={<ChartLine className="w-5 h-5 text-cyan-400" />} title="전략C: CHNG_DT 폴링 트렌드" />
        {chngDtTrend && chngDtTrend.entries.length > 0 ? (
          <div>
            {/* Summary stats */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              <div className="text-center p-3 rounded-lg bg-background">
                <div className="text-2xl font-bold text-cyan-400">{chngDtTrend.latest_total.toLocaleString()}</div>
                <div className="text-xs text-text-muted mt-1">API 전체 건수</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-background">
                <div className="text-2xl font-bold text-brand">{chngDtTrend.total_inserted}</div>
                <div className="text-xs text-text-muted mt-1">신규 INSERT</div>
              </div>
              <div className="text-center p-3 rounded-lg bg-background">
                <div className="text-lg font-bold text-text-primary">
                  {chngDtTrend.target_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3')}
                </div>
                <div className="text-xs text-text-muted mt-1">조회 대상일</div>
              </div>
            </div>

            {/* Line chart */}
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={chngDtTrend.entries.map(e => ({
                    time: e.polled_at.slice(11, 16),
                    total: e.total_api_count,
                    inserted: e.new_inserted,
                    elapsed: e.elapsed_sec,
                  }))}
                  margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                  <XAxis
                    dataKey="time"
                    tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  />
                  <YAxis
                    yAxisId="left"
                    tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                    tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--surface)',
                      border: '1px solid var(--border-standard)',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(value: number, name: string) => [
                      name === 'total' ? `${value.toLocaleString()}건` : `${value}건`,
                      name === 'total' ? 'API 전체' : '신규 INSERT'
                    ]}
                  />
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="total"
                    stroke="#06b6d4"
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#06b6d4' }}
                    name="total"
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="inserted"
                    stroke="#3ecf8e"
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#3ecf8e' }}
                    name="inserted"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Legend */}
            <div className="flex items-center justify-center gap-6 mt-2 text-xs text-text-muted">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-0.5 bg-cyan-400 rounded" />
                API 전체 건수
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-0.5 bg-brand rounded" />
                신규 INSERT
              </div>
            </div>

            {/* Poll history log */}
            {chngDtTrend.entries.length > 0 && (
              <div className="mt-4">
                <h3 className="text-xs font-medium text-text-muted mb-2">최근 폴링 이력</h3>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {[...chngDtTrend.entries].reverse().slice(0, 10).map((e, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-1.5 rounded bg-background text-xs">
                      <span className="text-text-muted font-mono">{e.polled_at.slice(11, 19)}</span>
                      <span className="text-text-primary">API {e.total_api_count.toLocaleString()}건</span>
                      <span className={`font-semibold ${e.new_inserted > 0 ? 'text-brand' : 'text-text-muted'}`}>
                        +{e.new_inserted}
                      </span>
                      <span className="text-text-muted">{e.elapsed_sec}s</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="h-40 flex items-center justify-center text-sm text-text-muted">
            폴링 데이터 수집 중... (CHNG_DT Poller 실행 후 표시됩니다)
          </div>
        )}
      </Card>

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
              {pageScan.entries.map((e) => {
                const hasTime = !!e.last_scanned;
                const hasFP = !!e.fingerprint;
                const colorClass = hasFP && hasTime
                  ? 'bg-brand hover:bg-brand/80'        // 이번 세션 스캔
                  : hasFP
                  ? 'bg-brand/30 hover:bg-brand/50'     // 이전 FP만
                  : 'bg-border-subtle hover:bg-border-standard'; // 미스캔
                return (
                  <div
                    key={e.page_number}
                    className={`w-3 h-3 rounded-[2px] transition-colors cursor-pointer ${colorClass}`}
                    title={`P${e.page_number} (${e.page_start.toLocaleString()}~)\n${hasFP ? `FP: ${e.fingerprint}` : '미스캔'}${hasTime ? `\n최종 스캔: ${e.last_scanned}` : ''}`}
                  />
                );
              })}
            </div>
            <div className="flex items-center gap-4 mt-3 text-xs text-text-muted">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-[2px] bg-brand" />
                이번 세션 스캔
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-[2px] bg-brand/30" />
                이전 FP
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
    </div>
  );
}
