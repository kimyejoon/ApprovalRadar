export interface ApprovalData {
  license_no: string;
  business_name: string;
  address: string;
  representative_name: string;
  business_status: string;
  license_date: string;
  phone_number: string;
  representative_history: any[];
  licensing_history: any[];
  last_event_date: string;
  created_at: string;
  updated_at: string;
  is_new: number;
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
