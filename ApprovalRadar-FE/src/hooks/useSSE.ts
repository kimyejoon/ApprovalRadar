import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToastStore } from '@/store/useToastStore';
import { useScanProgressStore } from '@/store/useScanProgressStore';
import { playNotificationSound } from '@/lib/audio';
import { fetchApprovals } from '@/lib/api';
import { CATEGORY_NAMES } from '@/lib/constants';
import { emitSystemAlert } from '@/lib/systemAlertEmitter';
import type { SystemAlertType } from '@/lib/systemAlertEmitter';

declare global {
  interface Window {
    triggerTestNotification?: () => Promise<void>;
  }
}

const envApiUrl = import.meta.env.VITE_API_URL;
const API_BASE_URL = envApiUrl !== undefined
  ? (envApiUrl === '' ? window.location.origin : envApiUrl)
  : 'http://localhost:8000';

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
        if (reconnectAttempts.current >= 5) {
          emitSystemAlert('WARN', '서버와의 연결이 복구되었습니다. 정상적으로 모니터링을 재개합니다.');
        }
        reconnectAttempts.current = 0;
      };

      // count만큼 최신 N건을 조회해 N개의 팝업을 토스트 큐에 적재
      const handleUpdateEvent = async (count = 1, isTest = false) => {
        try {
          const response = await fetchApprovals({
            page: 1,
            size: count,          // ← 백엔드가 전달한 변동 건수만큼 조회
            sort_by: 'updated_at',
            sort_order: 'desc',
          });

          if (!response.data || response.data.length === 0) return;

          // 최신순 수신 → 역순 적재 (큐: 오래된 것이 먼저 보임)
          const items = [...response.data].reverse();

          for (const item of items) {
            const statusName = item.infer_update_type
              ? CATEGORY_NAMES[item.infer_update_type] || item.infer_update_type
              : '상태 변경';

            const metadata: Array<{ label: string; value: string }> = [];
            if (item.industry_type)
              metadata.push({ label: '업종', value: item.industry_type });
            if (item.representative_name) {
              const prevRep = item.prev_representative_name
                ? ` (이전: ${item.prev_representative_name})`
                : '';
              metadata.push({ label: '대표자', value: `${item.representative_name}${prevRep}` });
            }
            if (item.phone_number)
              metadata.push({ label: '연락처', value: item.phone_number });
            if (item.business_status) {
              const prevStatus = item.prev_business_status
                ? ` (이전: ${item.prev_business_status})`
                : '';
              metadata.push({ label: '영업상태', value: `${item.business_status}${prevStatus}` });
            }
            if (item.infer_update_detail || item.update_type) {
              metadata.push({
                label: '변경 상세내역',
                value: item.infer_update_detail || item.update_type || '',
              });
            }

            addToast({
              title: isTest ? '[테스트] 새로운 인허가 변동 감지!' : '새로운 인허가 변동 감지!',
              description: `[${statusName}] ${item.business_name} (${item.address})`,
              type: 'default',
              duration: 0,
              metadata,
            });
          }

          // 알림음은 건수와 무관하게 1회만
          playNotificationSound();

          queryClient.invalidateQueries({ queryKey: ['approvals'] });
          queryClient.invalidateQueries({ queryKey: ['indicators'] });

          if (isTest) {
            console.log(`Test notification: ${items.length}건 팝업 적재 완료`);
          }
        } catch (err) {
          console.error('Failed to fetch latest data:', err);
        }
      };

      eventSource.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'UPDATE') {
            // 백엔드 SSE 페이로드에 count 포함 → N개 팝업 생성
            const count = typeof data.count === 'number' && data.count > 0 ? data.count : 1;
            await handleUpdateEvent(count);
          } else if (data.type === 'PLAYGROUND_UPDATE') {
            // Oldest-First Scan 페이지 완료 → 플레이그라운드 캐시 무효화 + 실시간 진행 스토어 업데이트
            queryClient.invalidateQueries({ queryKey: ['playgroundSummary'] });
            if (data.page && data.stats && data.cycle) {
              useScanProgressStore.getState().updatePage({
                page: data.page,
                label: data.page_label ?? null,
                stats: data.stats,
                cycle: data.cycle,
                scanned_at: new Date().toISOString(),
              });
            }
          } else if (data.type === 'WARN' || data.type === 'ALERT') {
            emitSystemAlert(data.type as SystemAlertType, data.message || '시스템 알림');
          }
        } catch {
          // JSON 파싱 실패 시 레거시 텍스트 메시지 호환
          if (event.data === '신규 업데이트가 발생했다') {
            await handleUpdateEvent(1);
          }
        }
      };


      eventSource.onerror = () => {
        eventSource.close();
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectAttempts.current += 1;

        // 5회 이상 연속 실패 시 크롤러 이상 팝업 (최초 1회만)
        if (reconnectAttempts.current === 5) {
          emitSystemAlert(
            'ALERT',
            '서버와의 연결이 끊겼습니다. 크롤링 로직에 이상이 발생한 것 같습니다.\n프로그램을 재시작하거나, 로그 화면을 캡처하여 개발자에게 문의해주세요.'
          );
        }

        setTimeout(connect, timeout);
      };

      // 개발 환경에서만 테스트 트리거 노출 (프로덕션 빌드 시 제거됨)
      if (import.meta.env.DEV && typeof window !== 'undefined') {
        window.triggerTestNotification = async () => {
          await handleUpdateEvent(1, true);
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
