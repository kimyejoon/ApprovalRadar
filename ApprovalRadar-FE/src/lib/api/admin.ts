import { API_BASE_URL } from './config';
import type { KeyStatusResponse, CrawlerStatusResponse } from './types';

export async function fetchKeyStatus(): Promise<KeyStatusResponse> {
  const url = `${API_BASE_URL}/api/v1/admin/key-status`;
  const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!response.ok) throw new Error('Failed to fetch key status');
  return response.json();
}

export async function fetchCrawlerStatus(): Promise<CrawlerStatusResponse> {
  const url = `${API_BASE_URL}/api/v1/admin/crawler-status`;
  const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!response.ok) throw new Error('Failed to fetch crawler status');
  return response.json();
}
