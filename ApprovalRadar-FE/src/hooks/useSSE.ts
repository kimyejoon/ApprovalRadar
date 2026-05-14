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
  const reconnectAttempts = useRef(0);

  useEffect(() => {
    const connect = () => {
      const url = `${API_BASE_URL}/api/v1/stream/updates`;
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        console.log('SSE Connection Opened:', url);
        reconnectAttempts.current = 0;
      };

      const handleUpdateEvent = async (isTest = false) => {
        try {
          const latestResponse = await fetchApprovals({
            page: 1,
            size: 1,
            sort_by: 'updated_at',
            sort_order: 'desc'
          });

          if (latestResponse.data && latestResponse.data.length > 0) {
            const latestItem = latestResponse.data[0];
            const statusName = latestItem.infer_update_type ? CATEGORY_NAMES[latestItem.infer_update_type] || latestItem.infer_update_type : '상태 변경';
            
            const metadata: Array<{label: string, value: string}> = [];
            if (latestItem.industry_type) metadata.push({ label: '업종', value: latestItem.industry_type });
            if (latestItem.representative_name) {
              const prevRep = latestItem.prev_representative_name ? ` (이전: ${latestItem.prev_representative_name})` : '';
              metadata.push({ label: '대표자', value: `${latestItem.representative_name}${prevRep}` });
            }
            if (latestItem.phone_number) metadata.push({ label: '연락처', value: latestItem.phone_number });
            if (latestItem.business_status) {
              const prevStatus = latestItem.prev_business_status ? ` (이전: ${latestItem.prev_business_status})` : '';
              metadata.push({ label: '영업상태', value: `${latestItem.business_status}${prevStatus}` });
            }
            if (latestItem.infer_update_detail || latestItem.update_type) {
               metadata.push({ label: '변경 상세내역', value: latestItem.infer_update_detail || latestItem.update_type || '' });
            }

            playNotificationSound();

            addToast({
              title: isTest ? `[테스트] 새로운 인허가 변동 감지!` : `새로운 인허가 변동 감지!`,
              description: `[${statusName}] ${latestItem.business_name} (${latestItem.address})`,
              type: 'default',
              duration: 0,
              metadata,
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
          const data = JSON.parse(event.data);
          if (data.type === 'UPDATE') {
            await handleUpdateEvent();
          }
        } catch {
          // JSON 파싱 실패 시 기존 텍스트 메시지 방식 호환 처리
          if (event.data === '신규 업데이트가 발생했다') {
            await handleUpdateEvent();
          }
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectAttempts.current += 1;
        setTimeout(connect, timeout);
      };

      // 개발 환경에서만 테스트 트리거 노출 (프로덕션 빌드 시 제거됨)
      if (import.meta.env.DEV && typeof window !== 'undefined') {
        window.triggerTestNotification = async () => {
          await handleUpdateEvent(true);
        };
      }
    };

    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        console.log('SSE Connection Closed');
      }
      if (import.meta.env.DEV && typeof window !== 'undefined') {
        delete window.triggerTestNotification;
      }
    };
  }, [addToast, queryClient]);

  return null;
}
