import { useState, useEffect, useCallback } from 'react';
import { fetchKeyStatus } from '@/lib/api';
import type { KeyStatusResponse } from '@/lib/api';

const POLL_INTERVAL_MS = 30_000; // 30초마다 폴링

export function useKeyStatus() {
  const [data, setData] = useState<KeyStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await fetchKeyStatus();
      setData(result);
      setLastUpdated(new Date());
    } catch {
      // 조용히 실패 (헤더 인디케이터는 비침습적이어야 함)
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  const activeCount = data?.keys.filter(k => k.status === 'active').length ?? 0;
  const exhaustedCount = data?.keys.filter(k => k.status === 'exhausted').length ?? 0;
  const errorCount = data?.keys.filter(k => k.status === 'error').length ?? 0;
  const totalCount = data?.total ?? 0;

  return { data, isLoading, lastUpdated, activeCount, exhaustedCount, errorCount, totalCount, refresh: load };
}
