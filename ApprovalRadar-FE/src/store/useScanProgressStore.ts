import { create } from 'zustand';

export interface PageStats {
  total_fetched: number;
  new_indexed: number;
  skipped_dup: number;
  today: number;
  yesterday: number;
}

export interface CycleInfo {
  elapsed_sec: number;
  api_calls: number;
  pages_done: number;
  pages_total: number;
  est_remaining_min: number;
}

export interface PageScanProgress {
  page: number;
  label: string | null;
  stats: PageStats;
  cycle: CycleInfo;
  scanned_at: string; // ISO timestamp
}

interface ScanProgressState {
  /** 현재 진행 중인 사이클의 최신 정보 */
  cycle: CycleInfo | null;
  /** 페이지 번호 → 마지막 스캔 결과 */
  pages: Record<number, PageScanProgress>;
  /** 마지막 PLAYGROUND_UPDATE 수신 시각 */
  lastUpdatedAt: string | null;

  updatePage: (progress: PageScanProgress) => void;
  reset: () => void;
}

export const useScanProgressStore = create<ScanProgressState>((set) => ({
  cycle: null,
  pages: {},
  lastUpdatedAt: null,

  updatePage: (progress) =>
    set((state) => ({
      cycle: progress.cycle,
      pages: { ...state.pages, [progress.page]: progress },
      lastUpdatedAt: progress.scanned_at,
    })),

  reset: () => set({ cycle: null, pages: {}, lastUpdatedAt: null }),
}));
