export interface JobStatus {
  job_id: string;
  name: string;
  next_run: string | null;
  seconds_remaining: number | null;
  is_running: boolean;
}

export interface SchedulerStatus {
  jobs: JobStatus[];
  current_time: string;
}

export interface TodayDetection {
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

export interface TailHistoryEntry {
  record_date: string;
  total_count: number;
}

export interface PageScanEntry {
  page_number: number;
  page_start: number;
  fingerprint: string | null;
  last_scanned: string | null;
  label?: string | null;
  industry?: string | null;  // 업종 (INDUTY_NM: 일반음식점, 휴게음식점, 제과점영업, 등)
}

export interface PageScanHistory {
  total_pages: number;
  scanned_pages: number;
  entries: PageScanEntry[];
}

export interface TailHistory {
  service_id: string;
  entries: TailHistoryEntry[];
}

/** 플레이그라운드 대시보드 통합 상태 (GET /api/v1/playground/summary 응답) */
export interface PlaygroundSummary {
  scheduler: SchedulerStatus;
  today: TodayDetection;
  tail_history: TailHistory;
  page_scan: PageScanHistory;
}

export interface ChngDtPollEntry {
  polled_at: string;
  total_api_count: number;
  new_inserted: number;
  already_exists: number;
  pages_fetched: number;
  elapsed_sec: number;
  api_raw_total_count: number;  // I2500 API 응답의 실제 total_count 필드
}

export interface ChngDtTrendResponse {
  target_date: string;
  entries: ChngDtPollEntry[];
  latest_total: number;
  total_inserted: number;
  yesterday_date: string;
  yesterday_entries: ChngDtPollEntry[];
  today_date: string;
  today_entries: ChngDtPollEntry[];
}

