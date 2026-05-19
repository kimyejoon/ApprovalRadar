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

const envApiUrl = import.meta.env.VITE_API_URL;
export const API_BASE_URL = envApiUrl !== undefined 
  ? (envApiUrl === '' ? window.location.origin : envApiUrl) 
  : 'http://localhost:8000';


export async function fetchApprovals(params: FetchApprovalsParams): Promise<ApprovalsResponse> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals`);
  
  // Append query parameters
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.append(key, String(value));
    }
  });

  const response = await fetch(url.toString(), {
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch approvals');
  }

  return response.json();
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

export async function fetchApprovalDetail(params: ApprovalDetailParams): Promise<ApprovalDetailResponse> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals/detail`);
  if (params.license_no) url.searchParams.append('license_no', params.license_no);
  if (params.license_date) url.searchParams.append('license_date', params.license_date);
  if (params.business_name) url.searchParams.append('business_name', params.business_name);

  const response = await fetch(url.toString(), {
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch approval detail');
  }

  return response.json();
}

export async function markApprovalAsRead(license_no: string): Promise<{ status: string }> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals/readInfo/${license_no}`);
  const response = await fetch(url.toString(), {
    method: 'PUT',
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error('Failed to mark approval as read');
  }

  return response.json();
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

export async function fetchIndicators(params: FetchIndicatorsParams): Promise<IndicatorResponse> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals/indicators`);
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.append(key, String(value));
    }
  });

  const response = await fetch(url.toString(), {
    headers: {
      'Accept': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch indicators');
  }

  return response.json();
}

export interface ExportApprovalsParams {
  start_date?: string;
  end_date?: string;
}

export async function exportApprovalsExcel(params: ExportApprovalsParams, customFilename?: string): Promise<void> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals/export`);
  
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.append(key, String(value));
    }
  });

  const response = await fetch(url.toString(), {
    method: 'GET',
  });

  if (!response.ok) {
    throw new Error('Failed to export excel');
  }

  // Use custom filename if provided, otherwise try to extract from header
  let filename = customFilename || 'approvals_export.xlsx';
  if (!customFilename) {
    const disposition = response.headers.get('content-disposition');
    if (disposition && disposition.includes('filename*=')) {
      const filenameMatch = disposition.split("filename*=UTF-8''")[1];
      if (filenameMatch) {
        filename = decodeURIComponent(filenameMatch);
      }
    } else if (disposition && disposition.includes('filename=')) {
      const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
      if (filenameMatch && filenameMatch.length > 1) {
        filename = filenameMatch[1];
      }
    }
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(downloadUrl);
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

export async function fetchKeyStatus(): Promise<KeyStatusResponse> {
  const url = `${API_BASE_URL}/api/v1/admin/key-status`;
  const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!response.ok) throw new Error('Failed to fetch key status');
  return response.json();
}

// ─── Crawler Status ────────────────────────────────────────────────────────

export interface CrawlerServiceStatus {
  service_id: string;
  service_name?: string;  // 사용자 친화적 서비스명 (BE에서 제공)
  last_total_count: number;
  updated_at: string | null;
}

export interface CrawlerStatusResponse {
  services: CrawlerServiceStatus[];
}

export async function fetchCrawlerStatus(): Promise<CrawlerStatusResponse> {
  const url = `${API_BASE_URL}/api/v1/admin/crawler-status`;
  const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!response.ok) throw new Error('Failed to fetch crawler status');
  return response.json();
}

// ─── Settings: API Key Management ─────────────────────────────────────────

export interface ApiKeyManagementItem {
  id: number;
  key_masked: string;
  memo: string | null;
  is_active: boolean;
  created_at: string;
  call_count_today: number;
  is_exhausted: boolean;
  crawl_resumed: boolean;  // 새 키 추가로 크롤링이 즉시 재개됐으면 true
}

export interface ApiKeyListResponse {
  total: number;
  keys: ApiKeyManagementItem[];
}

export async function fetchApiKeys(): Promise<ApiKeyListResponse> {
  const url = `${API_BASE_URL}/api/v1/admin/settings/api-keys`;
  const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!response.ok) throw new Error('Failed to fetch API keys');
  return response.json();
}

export async function createApiKey(key_value: string, memo?: string): Promise<ApiKeyManagementItem> {
  const url = `${API_BASE_URL}/api/v1/admin/settings/api-keys`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({ key_value, memo }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create API key');
  }
  return response.json();
}

export async function updateApiKey(id: number, data: { memo?: string; is_active?: boolean }): Promise<ApiKeyManagementItem> {
  const url = `${API_BASE_URL}/api/v1/admin/settings/api-keys/${id}`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update API key');
  return response.json();
}

export async function deleteApiKey(id: number): Promise<void> {
  const url = `${API_BASE_URL}/api/v1/admin/settings/api-keys/${id}`;
  const response = await fetch(url, { method: 'DELETE', headers: { 'Accept': 'application/json' } });
  if (!response.ok) throw new Error('Failed to delete API key');
}

// ─── 메모 (인허가 이력 건별 메모) ─────────────────────────────────────────────

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

export async function fetchMemo(params: MemoParams): Promise<MemoResponse> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals/memo`);
  url.searchParams.append('license_date', params.license_date);
  url.searchParams.append('business_name', params.business_name);
  const response = await fetch(url.toString(), { headers: { 'Accept': 'application/json' } });
  if (!response.ok) throw new Error('Failed to fetch memo');
  return response.json();
}

export async function createMemo(params: MemoParams & { content: string }): Promise<MemoResponse> {
  const url = `${API_BASE_URL}/api/v1/approvals/memo`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to create memo');
  }
  return response.json();
}

export async function updateMemo(params: MemoParams & { content: string }): Promise<MemoResponse> {
  const url = `${API_BASE_URL}/api/v1/approvals/memo`;
  const response = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error('Failed to update memo');
  return response.json();
}

export async function deleteMemo(params: MemoParams): Promise<void> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals/memo`);
  url.searchParams.append('license_date', params.license_date);
  url.searchParams.append('business_name', params.business_name);
  const response = await fetch(url.toString(), {
    method: 'DELETE',
    headers: { 'Accept': 'application/json' },
  });
  if (!response.ok) throw new Error('Failed to delete memo');
}
