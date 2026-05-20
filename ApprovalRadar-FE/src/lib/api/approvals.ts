import { API_BASE_URL } from './config';
import type {
  FetchApprovalsParams,
  ApprovalsResponse,
  ApprovalDetailParams,
  ApprovalDetailResponse,
  FetchIndicatorsParams,
  IndicatorResponse,
  ExportApprovalsParams,
} from './types';

export async function fetchApprovals(params: FetchApprovalsParams): Promise<ApprovalsResponse> {
  const url = new URL(`${API_BASE_URL}/api/v1/approvals`);
  
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
