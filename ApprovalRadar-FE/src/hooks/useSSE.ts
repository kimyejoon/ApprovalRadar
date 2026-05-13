import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToastStore } from '@/store/useToastStore';
import { playNotificationSound } from '@/lib/audio';
import { fetchApprovals } from '@/lib/api';
import { CATEGORY_NAMES } from '@/lib/constants';

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

    eventSource.onmessage = async (event) => {
      try {
        const rawData = event.data;
        // 백엔드에서 5초마다 보내는 Keep-Alive 핑 무시
        if (!rawData || rawData === 'ping' || rawData === 'keep-alive') {
          return;
        }

        // 실질적인 업데이트 이벤트 감지
        // 백엔드가 단순히 "업데이트 발생"만 알려주는 구조이므로, 
        // 최신 1건을 즉시 Fetch 해옴
        const latestResponse = await fetchApprovals({
          page: 1,
          size: 1,
          sort_by: 'created_at',
          sort_order: 'desc'
        });

        if (latestResponse.data && latestResponse.data.length > 0) {
          const latestItem = latestResponse.data[0];
          const statusName = latestItem.infer_update_type ? CATEGORY_NAMES[latestItem.infer_update_type] || latestItem.infer_update_type : '상태 변경';
          
          // 2. 알림음 재생
          playNotificationSound();

          // 3. 토스트 알림 띄우기
          addToast({
            title: `새로운 인허가 변동 감지!`,
            description: `[${statusName}] ${latestItem.business_name} (${latestItem.address})`,
            type: 'default',
            duration: 8000,
          });

          // 4. 대시보드의 데이터 캐시 무효화 (자동 새로고침)
          queryClient.invalidateQueries({ queryKey: ['approvals'] });
          queryClient.invalidateQueries({ queryKey: ['indicators'] });
        }
      } catch (err) {
        console.error('Failed to process SSE message or fetch latest data:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Connection Error:', err);
      // 에러 발생 시 EventSource는 브라우저 정책에 따라 자동 재연결을 시도함
    };

    // Chrome Console 테스트용 함수 노출
    if (typeof window !== 'undefined') {
      (window as any).triggerTestNotification = async () => {
        playNotificationSound();
        addToast({
          title: "테스트: 새로운 인허가 변동 감지!",
          description: "[신규] 테스트식당 (서울특별시 강남구 테헤란로)",
          type: "default",
          duration: 5000,
        });
        // 캐시 무효화 시뮬레이션
        queryClient.invalidateQueries({ queryKey: ['approvals'] });
        console.log("Test notification triggered and query cache invalidated.");
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
        delete (window as any).triggerTestNotification;
      }
    };
  }, [addToast, queryClient]);

  return null;
}
