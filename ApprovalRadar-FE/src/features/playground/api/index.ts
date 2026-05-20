import { API_BASE_URL } from '@/lib/api';
import type { SchedulerStatus, TodayDetection, TailHistoryEntry, PageScanHistoryResponse } from '../types';

const BASE = `${API_BASE_URL}/api/v1/playground`;

export async function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  const res = await fetch(`${BASE}/scheduler-status`);
  if (!res.ok) throw new Error('Failed to fetch scheduler status');
  return res.json();
}

export async function triggerJob(jobType: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/trigger/${jobType}`, { method: 'POST' });
  return res.json();
}

export async function triggerRangeScan(start: number, end: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/trigger/range-scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end }),
  });
  return res.json();
}

export async function fetchTodayDetection(): Promise<TodayDetection> {
  const res = await fetch(`${BASE}/today-detection/I2861`);
  if (!res.ok) throw new Error('Failed to fetch today detection');
  return res.json();
}

export async function fetchTailHistory(): Promise<TailHistoryEntry[]> {
  const res = await fetch(`${BASE}/tail-history/I2861`);
  if (!res.ok) throw new Error('Failed to fetch tail history');
  const data = await res.json();
  return data.entries;
}

export async function fetchPageScanHistory(): Promise<PageScanHistoryResponse> {
  const res = await fetch(`${BASE}/page-scan-history/I2861`);
  if (!res.ok) throw new Error('Failed to fetch page scan history');
  return res.json();
}
