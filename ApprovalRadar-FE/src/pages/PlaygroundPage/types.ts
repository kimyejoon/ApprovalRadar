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
}

export interface SmartSweepLogEntry {
  run_at: string;
  strategy: string;
  probe_calls: number;
  hot_segs: number;
  collected: number;
  elapsed_sec: number;
  detail: { seg: string; class: string; first_chng: string }[];
}

export interface SmartSweepCache {
  total_cached: number;
  hot: number;
  warm: number;
  cold: number;
  segments: { seg: string; total_count: number; first_chng: string; cls: string; probed_at: string }[];
}
