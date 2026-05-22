import { create } from 'zustand';

export type ApiHealthStatus = 'NORMAL' | 'SLOW' | 'DEGRADED' | 'UNSTABLE' | 'UNKNOWN';

export interface ApiHealthMetrics {
  avg_response_ms: number;
  timeout_count: number;
  waf_block_count: number;
  max_retry_count: number;
  total_calls: number;
  success_rate: number;
}

export interface ApiHealthState {
  status: ApiHealthStatus;
  status_changed_at: string | null;
  window_seconds: number;
  metrics: ApiHealthMetrics | null;
  last_updated: string | null;

  setHealth: (payload: {
    status: ApiHealthStatus;
    status_changed_at?: string;
    window_seconds?: number;
    metrics?: ApiHealthMetrics;
  }) => void;
}

export const useApiHealthStore = create<ApiHealthState>((set) => ({
  status: 'UNKNOWN',
  status_changed_at: null,
  window_seconds: 300,
  metrics: null,
  last_updated: null,

  setHealth: (payload) =>
    set({
      status: payload.status ?? 'UNKNOWN',
      status_changed_at: payload.status_changed_at ?? null,
      window_seconds: payload.window_seconds ?? 300,
      metrics: payload.metrics ?? null,
      last_updated: new Date().toISOString(),
    }),
}));
