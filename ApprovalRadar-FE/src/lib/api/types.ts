export interface ApprovalData {
  license_no: string;
  business_name: string;
  address: string;
  representative_name: string;
  business_status: string;
  license_date: string;
  phone_number: string;
  representative_history: unknown[];
  licensing_history: unknown[];
  industry_type?: string | null;
  last_event_date: string;
  created_at: string;
  updated_at: string;
  is_new: number;
  update_type?: string;
  prev_business_status?: string | null;
  prev_representative_name?: string | null;
  prev_business_name?: string | null;
  infer_update_type?: string;
  infer_update_detail?: string;
  is_read?: number;
  read_at?: string | null;
  collected_by?: string | null;
}

export interface ApprovalMappedItem {
  id: string;
  name: string;
  prevName?: string | null;
  type: string;
  location: string;
  owner: string;
  prevOwner?: string | null;
  status: string;
  updateDetail?: string;
  approvalDate: string;
  phone: string;
  isTransfer: boolean;
  isRead: boolean;
  raw: ApprovalData;
}

export interface ApprovalsResponse {
  status: string;
  data: ApprovalData[];
  meta: {
    total_count: number;
    current_page: number;
    total_pages: number;
    size: number;
  };
}

export interface FetchApprovalsParams {
  page?: number;
  size?: number;
  search?: string;
  start_date?: string;
  end_date?: string;
  regions?: string;
  infer_update_type?: string;
  industry_type?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface ApprovalDetailParams {
  license_no?: string;
  license_date?: string;
  business_name?: string;
}

export interface ApprovalDetailResponse {
  status: string;
  data: ApprovalData[];
}

export interface FetchIndicatorsParams {
  search?: string;
  start_date?: string;
  end_date?: string;
  regions?: string;
}

export interface StatusDistribution {
  name: string;
  value: number;
}

export interface TrendChart {
  date: string;
  count: number;
}

export interface IndicatorData {
  total_approvals: number;
  monthly_approvals: number;
  today_approvals: number;
  status_distribution: StatusDistribution[];
  trend_chart: TrendChart[];
}

export interface IndicatorResponse {
  status: string;
  data: IndicatorData;
}

export interface ExportApprovalsParams {
  start_date?: string;
  end_date?: string;
}

export interface KeyStatusItem {
  index: number;
  masked_key: string;
  status: 'active' | 'exhausted' | 'error';
  status_label: string;
  code?: string;
  message?: string;
}

export interface KeyStatusResponse {
  total: number;
  keys: KeyStatusItem[];
}

export interface CrawlerServiceStatus {
  service_id: string;
  service_name?: string;
  last_total_count: number;
  updated_at: string | null;
}

export interface CrawlerStatusResponse {
  services: CrawlerServiceStatus[];
}

export interface ApiKeyManagementItem {
  id: number;
  key_masked: string;
  memo: string | null;
  is_active: boolean;
  created_at: string;
  call_count_today: number;
  is_exhausted: boolean;
  crawl_resumed: boolean;
}

export interface ApiKeyListResponse {
  total: number;
  keys: ApiKeyManagementItem[];
}

export interface MemoData {
  id: number;
  license_date: string;
  business_name: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface MemoResponse {
  status: string;
  data: MemoData | null;
}

export interface MemoParams {
  license_date: string;
  business_name: string;
}
