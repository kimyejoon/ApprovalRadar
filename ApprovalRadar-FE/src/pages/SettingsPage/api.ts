import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchApiKeys,
  createApiKey,
  updateApiKey,
  deleteApiKey,
} from '@/lib/api';

const API_BASE = '';

// ─── Crawl Interval API ───
export async function fetchCrawlInterval(): Promise<number> {
  const res = await fetch(`${API_BASE}/api/v1/admin/settings/crawl-interval`);
  if (!res.ok) throw new Error('크롤 주기 조회 실패');
  const data = await res.json();
  return data.interval_minutes;
}

export async function updateCrawlInterval(minutes: number): Promise<number> {
  const res = await fetch(`${API_BASE}/api/v1/admin/settings/crawl-interval`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_minutes: minutes }),
  });
  if (!res.ok) throw new Error('크롤 주기 변경 실패');
  const data = await res.json();
  return data.interval_minutes;
}

// ─── Rolling Scan API ───
export async function fetchRollingScanRate(): Promise<number> {
  const res = await fetch(`${API_BASE}/api/v1/admin/settings/rolling-scan-rate`);
  if (!res.ok) throw new Error('스캔 속도 조회 실패');
  const data = await res.json();
  return data.pages_per_cycle;
}

export async function updateRollingScanRate(pages: number): Promise<number> {
  const res = await fetch(`${API_BASE}/api/v1/admin/settings/rolling-scan-rate`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pages_per_cycle: pages }),
  });
  if (!res.ok) throw new Error('스캔 속도 변경 실패');
  const data = await res.json();
  return data.pages_per_cycle;
}

// ─── Custom React-Query Hooks ───
export function useApiKeysQuery() {
  return useQuery({
    queryKey: ['settings-api-keys'],
    queryFn: fetchApiKeys,
    refetchInterval: 60_000,
  });
}

export function useCreateApiKeyMutation() {
  return useMutation({
    mutationFn: ({ key, memo }: { key: string; memo?: string }) => createApiKey(key, memo),
  });
}

export function useUpdateApiKeyMemoMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, memo }: { id: number; memo: string }) => updateApiKey(id, { memo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings-api-keys'] });
    },
  });
}

export function useToggleApiKeyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      updateApiKey(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings-api-keys'] });
    },
  });
}

export function useDeleteApiKeyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings-api-keys'] });
    },
  });
}

export function useCrawlIntervalQuery() {
  return useQuery<number>({
    queryKey: ['crawl-interval'],
    queryFn: fetchCrawlInterval,
  });
}

export function useUpdateCrawlIntervalMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (minutes: number) => updateCrawlInterval(minutes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crawl-interval'] });
    },
  });
}

export function useRollingScanRateQuery() {
  return useQuery<number>({
    queryKey: ['rolling-scan-rate'],
    queryFn: fetchRollingScanRate,
  });
}

export function useUpdateRollingScanRateMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pages: number) => updateRollingScanRate(pages),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rolling-scan-rate'] });
    },
  });
}
