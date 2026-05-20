import { useState, useEffect, useCallback } from 'react';
import type { SchedulerStatus, TodayDetection, TailHistoryEntry, PageScanHistoryResponse } from '../types';
import {
  fetchSchedulerStatus,
  fetchTodayDetection,
  fetchTailHistory,
  fetchPageScanHistory,
  triggerJob,
  triggerRangeScan
} from '../api';

export function usePlayground() {
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [today, setToday] = useState<TodayDetection | null>(null);
  const [tailHistory, setTailHistory] = useState<TailHistoryEntry[]>([]);
  const [pageScan, setPageScan] = useState<PageScanHistoryResponse | null>(null);

  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [rangeStart, setRangeStart] = useState<string>('1');
  const [rangeEnd, setRangeEnd] = useState<string>('10000');

  const refresh = useCallback(async () => {
    try {
      const [sched, det, tail, pages] = await Promise.all([
        fetchSchedulerStatus(),
        fetchTodayDetection(),
        fetchTailHistory(),
        fetchPageScanHistory(),
      ]);
      setScheduler(sched);
      setToday(det);
      setTailHistory(tail);
      setPageScan(pages);
    } catch (e) {
      console.error('Playground refresh failed:', e);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
    const timer = setInterval(refresh, 10000); // 10초 자동 갱신
    return () => clearInterval(timer);
  }, [refresh]);

  const handleTrigger = async (jobType: string) => {
    setLoading(true);
    setTriggerMsg(null);
    try {
      const result = await triggerJob(jobType);
      setTriggerMsg(result.message);
      setTimeout(() => setTriggerMsg(null), 5000);
    } catch {
      setTriggerMsg('트리거 실패');
    } finally {
      setLoading(false);
    }
  };

  const handleRangeScan = async () => {
    const s = parseInt(rangeStart, 10);
    const e = parseInt(rangeEnd, 10);
    if (isNaN(s) || isNaN(e) || s < 1 || e < s) {
      setTriggerMsg('잘못된 범위입니다');
      setTimeout(() => setTriggerMsg(null), 3000);
      return;
    }
    setLoading(true);
    setTriggerMsg(null);
    try {
      const result = await triggerRangeScan(s, e);
      setTriggerMsg(result.message);
      setTimeout(() => setTriggerMsg(null), 5000);
    } catch {
      setTriggerMsg('Range Scan 트리거 실패');
    } finally {
      setLoading(false);
    }
  };

  return {
    scheduler,
    today,
    tailHistory,
    pageScan,
    triggerMsg,
    loading,
    rangeStart,
    rangeEnd,
    setRangeStart,
    setRangeEnd,
    refresh,
    handleTrigger,
    handleRangeScan,
  };
}
