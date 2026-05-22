import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToastStore } from '@/store/useToastStore';
import { useApiHealthStore } from '@/store/useApiHealthStore';
import { useScanProgressStore } from '@/store/useScanProgressStore';
import { playNotificationSound } from '@/lib/audio';
import { fetchApprovals } from '@/lib/api';
import { CATEGORY_NAMES } from '@/lib/constants';
import { emitSystemAlert } from '@/lib/systemAlertEmitter';
import type { SystemAlertType } from '@/lib/systemAlertEmitter';
import type { NotificationOptions } from './useNotification';

declare global {
  interface Window {
    triggerTestNotification?: () => Promise<void>;
  }
}

const envApiUrl = import.meta.env.VITE_API_URL;
const API_BASE_URL = envApiUrl !== undefined
  ? (envApiUrl === '' ? window.location.origin : envApiUrl)
  : 'http://localhost:8000';

export function useSSE(sendNotification?: (opts: NotificationOptions) => void) {
  const queryClient = useQueryClient();
  const addToast = useToastStore((state) => state.addToast);
  const setHealth = useApiHealthStore((s) => s.setHealth);
  const prevHealthStatus = useRef<string | null>(null);
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
          const allItems = [...response.data].reverse();

          // 대표자변경 이면서 업종 3종(기본필터)인 경우에만 알림/토스트 노출
          const items = allItems.filter((item: any) =>
            item.infer_update_type === '대표자변경' &&
            ['일반음식점', '제과점영업', '휴게음식점'].includes(item.industry_type || '')
          );

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

          if (items.length > 0) {
            // 알림음은 건수와 무관하게 1회만
            playNotificationSound();

            // 브라우저 Web Notification (탭 백그라운드일 때만)
            if (sendNotification) {
              const first = items[items.length - 1]; // 가장 최신 건
              const statusName = first.infer_update_type
                ? CATEGORY_NAMES[first.infer_update_type] || first.infer_update_type
                : '상태 변경';
              sendNotification({
                title: `🔔 인허가 변동 ${items.length}건 감지`,
                body: `[${statusName}] ${first.business_name} (${first.address})`,
              });
            }
          }

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

          // PING에 포함된 api_health 처리 (5초마다 자동 갱신)
          if (data.api_health && data.api_health.status) {
            const h = data.api_health;
            const newStatus = h.status;
            setHealth(h);

            // 상태 변경 시 토스트 알림
            if (prevHealthStatus.current !== null && prevHealthStatus.current !== newStatus) {
              const STATUS_LABEL: Record<string, string> = {
                NORMAL: '정상', SLOW: '느림', DEGRADED: '저하', UNSTABLE: '불안정',
              };
              const STATUS_TOAST_TYPE: Record<string, 'success' | 'warning' | 'error'> = {
                NORMAL: 'success', SLOW: 'warning', DEGRADED: 'warning', UNSTABLE: 'error',
              };
              const STATUS_DESC: Record<string, string> = {
                NORMAL: '식품안전나라 API 서버가 정상 응답 중입니다.',
                SLOW: '응답이 다소 느립니다. 데이터 수집 속도가 저하될 수 있습니다.',
                DEGRADED: '다수의 타임아웃이 감지됐습니다. 수집 지연이 발생 중입니다.',
                UNSTABLE: 'API 서버가 불안정합니다. WAF 차단 또는 최대 재시도 초과 발생.',
              };
              addToast({
                title: `외부 API 서버 상태: ${STATUS_LABEL[newStatus] ?? newStatus}`,
                description: STATUS_DESC[newStatus] ?? '',
                type: STATUS_TOAST_TYPE[newStatus] ?? 'info',
                duration: 8000,
                metadata: h.metrics ? [
                  { label: '평균 응답', value: `${h.metrics.avg_response_ms.toLocaleString()}ms` },
                  { label: '타임아웃',  value: `${h.metrics.timeout_count}건` },
                  { label: '성공률',    value: `${h.metrics.success_rate}%` },
                  { label: 'WAF 차단',  value: `${h.metrics.waf_block_count}건` },
                ] : undefined,
              });
            }
            prevHealthStatus.current = newStatus;
          }

          if (data.type === 'UPDATE') {
            // 백엔드 SSE 페이로드에 count 포함 → N개 팝업 생성
            const count = typeof data.count === 'number' && data.count > 0 ? data.count : 1;
            await handleUpdateEvent(count);
          } else if (data.type === 'PLAYGROUND_UPDATE') {
            // Oldest-First Scan 페이지 완료 → 플레이그라운드 캐시 무효화 + 실시간 진행 스토어 업데이트
            // NOTE: chngDtTrend는 여기서 invalidate 하지 않음 — PLAYGROUND_UPDATE는 I2861 페이지
            //       완료마다 발생(초당 수회)하므로 chngDtTrend의 자체 refetchInterval(10초)에 맡김
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
  }, [addToast, queryClient, sendNotification]);

  return null;
}
