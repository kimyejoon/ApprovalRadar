import { API_BASE_URL } from '@/lib/api';
import type { PlaygroundSummary, ChngDtTrendResponse } from './types';

const BASE = `${API_BASE_URL}/api/v1/playground`;

/** 플레이그라운드 대시보드 전체 상태를 단일 요청으로 조회합니다. */
export async function fetchPlaygroundSummary(serviceId = 'I2861'): Promise<PlaygroundSummary> {
  const res = await fetch(`${BASE}/summary?service_id=${serviceId}`);
  if (!res.ok) throw new Error('Failed to fetch playground summary');
  return res.json();
}

/** CHNG_DT 폴러 시간별 트렌드 데이터를 조회합니다. */
export async function fetchChngDtTrend(): Promise<ChngDtTrendResponse> {
  const res = await fetch(`${BASE}/chng-dt-trend`);
  if (!res.ok) throw new Error('Failed to fetch chng-dt trend data');
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
