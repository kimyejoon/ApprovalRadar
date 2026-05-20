import { API_BASE_URL } from './config';
import type { MemoParams, MemoResponse } from './types';

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
