import { API_BASE_URL } from './config';
import type { ApiKeyListResponse, ApiKeyManagementItem } from './types';

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
