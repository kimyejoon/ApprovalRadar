/**
 * useNotification: 브라우저 Web Notification API 권한 관리 훅
 *
 * - 마운트 시 권한이 'default'이면 권한 요청 프롬프트 표시
 * - sendNotification()으로 언제든 알림 발행 가능
 * - 탭이 포커스 상태이면 알림 억제 (토스트로 이미 표시됨)
 */
import { useEffect, useCallback, useRef } from 'react';

export interface NotificationOptions {
  title: string;
  body: string;
  icon?: string;
}

export function useNotification() {
  const permissionRef = useRef<NotificationPermission>(
    typeof Notification !== 'undefined' ? Notification.permission : 'denied'
  );

  // 최초 마운트 시 권한 요청
  useEffect(() => {
    if (typeof Notification === 'undefined') return;
    if (Notification.permission === 'default') {
      Notification.requestPermission().then((result) => {
        permissionRef.current = result;
        if (result === 'granted') {
          console.info('[Notification] 알림 권한 승인됨');
        }
      });
    } else {
      permissionRef.current = Notification.permission;
    }
  }, []);

  const sendNotification = useCallback(
    ({ title, body, icon = '/logo.png' }: NotificationOptions) => {
      if (typeof Notification === 'undefined') return;
      if (permissionRef.current !== 'granted') return;

      // 탭이 포커스 상태이면 브라우저 알림 억제 (앱 내 토스트로 충분)
      if (document.visibilityState === 'visible') return;

      try {
        const n = new Notification(title, { body, icon });
        // 알림 클릭 시 탭 포커스
        n.onclick = () => {
          window.focus();
          n.close();
        };
        // 8초 후 자동 닫기
        setTimeout(() => n.close(), 8000);
      } catch (e) {
        console.warn('[Notification] 발송 실패:', e);
      }
    },
    []
  );

  return { sendNotification };
}
