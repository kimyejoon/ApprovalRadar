import { API_BASE_URL } from '@/lib/api';
import type {
  SchedulerStatus,
  TodayDetection,
  TailHistoryEntry,
  PageScanEntry,
  SmartSweepLogEntry,
  SmartSweepCache,
} from './types';

const BASE = `${API_BASE_URL}/api/v1/playground`;

export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  const res = await fetch(`${BASE}/scheduler-status`);
  if (!res.ok) throw new Error('Failed scheduler status fetch');
  return res.json();
}

export async function triggerJob(jobType: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/trigger/${jobType}`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger job');
  return res.json();
}

export async function triggerRangeScan(start: number, end: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/trigger/range-scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end }),
  });
  if (!res.ok) throw new Error('Failed to trigger range scan');
  return res.json();
}

export async function fetchTodayDetection(): Promise<TodayDetection> {
  const res = await fetch(`${BASE}/today-detection/I2861`);
  if (!res.ok) throw new Error('Failed today detection fetch');
  return res.json();
}

export async function fetchTailHistory(): Promise<TailHistoryEntry[]> {
  const res = await fetch(`${BASE}/tail-history/I2861`);
  if (!res.ok) throw new Error('Failed tail history fetch');
  const data = await res.json();
  return data.entries;
}

export async function fetchPageScanHistory(): Promise<{ total_pages: number; scanned_pages: number; entries: PageScanEntry[] }> {
  const res = await fetch(`${BASE}/page-scan-history/I2861`);
  if (!res.ok) throw new Error('Failed page scan history fetch');
  return res.json();
}

export async function fetchSmartSweepStatus(): Promise<{ entries: SmartSweepLogEntry[]; count: number }> {
  const res = await fetch(`${BASE}/smart-sweep/status`);
  if (!res.ok) return { entries: [], count: 0 };
  return res.json();
}

export async function fetchSmartSweepCache(): Promise<SmartSweepCache> {
  const res = await fetch(`${BASE}/smart-sweep/cache`);
  if (!res.ok) return { total_cached: 0, hot: 0, warm: 0, cold: 0, segments: [] };
  return res.json();
}
