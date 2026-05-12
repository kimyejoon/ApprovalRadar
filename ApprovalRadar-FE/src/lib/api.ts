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
  last_event_date: string;
  created_at: string;
  updated_at: string;
  is_new: number;
}

export interface ApprovalMappedItem {
  id: string;
  name: string;
  type: string;
  location: string;
  owner: string;
  status: string;
  approvalDate: string;
  phone: string;
  isTransfer: boolean;
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
  statuses?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

export async function exportApprovalsExcel(params: ExportApprovalsParams): Promise<void> {
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

  // Extract filename from Content-Disposition header if possible
  let filename = 'approvals_export.xlsx';
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
