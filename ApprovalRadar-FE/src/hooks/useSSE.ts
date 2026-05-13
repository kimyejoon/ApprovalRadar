import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToastStore } from '@/store/useToastStore';
import { playNotificationSound } from '@/lib/audio';
import { fetchApprovals } from '@/lib/api';
import { CATEGORY_NAMES } from '@/lib/constants';

declare global {
  interface Window {
    triggerTestNotification?: () => Promise<void>;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function useSSE() {
  const queryClient = useQueryClient();
  const addToast = useToastStore((state) => state.addToast);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // 1. SSE 연결 시작
    const url = `${API_BASE_URL}/api/v1/stream/updates`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      console.log('SSE Connection Opened:', url);
    };

    const handleUpdateEvent = async (isTest = false) => {
      try {
        const latestResponse = await fetchApprovals({
          page: 1,
          size: 1,
          sort_by: 'created_at',
          sort_order: 'desc'
        });

        if (latestResponse.data && latestResponse.data.length > 0) {
          const latestItem = latestResponse.data[0];
          const statusName = latestItem.infer_update_type ? CATEGORY_NAMES[latestItem.infer_update_type] || latestItem.infer_update_type : '상태 변경';
          
          playNotificationSound();

          addToast({
            title: isTest ? `[테스트] 새로운 인허가 변동 감지!` : `새로운 인허가 변동 감지!`,
            description: `[${statusName}] ${latestItem.business_name} (${latestItem.address})`,
            type: 'default',
            duration: 0,
          });

          queryClient.invalidateQueries({ queryKey: ['approvals'] });
          queryClient.invalidateQueries({ queryKey: ['indicators'] });
          if (isTest) {
            console.log("Test notification triggered and query cache invalidated with real data.");
          }
        }
      } catch (err) {
        console.error('Failed to fetch latest data:', err);
      }
    };

    eventSource.onmessage = async (event) => {
      try {
        const rawData = event.data;
        
        if (!rawData || rawData.includes('현재 정상 연결중임')) {
          return;
        }

        if (!rawData.includes('신규 업데이트가 발생했다')) {
          return;
        }

        await handleUpdateEvent();
      } catch (err) {
        console.error('Failed to process SSE message:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Connection Error:', err);
    };

    if (typeof window !== 'undefined') {
      window.triggerTestNotification = async () => {
        await handleUpdateEvent(true);
      };
      console.log(`💡 테스트 방법: 크롬 개발자 도구 콘솔에서 'window.triggerTestNotification()' 입력`);
    }

    // 언마운트 시 SSE 연결 종료
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        console.log('SSE Connection Closed');
      }
      if (typeof window !== 'undefined') {
        delete window.triggerTestNotification;
      }
    };
  }, [addToast, queryClient]);

  return null;
}
