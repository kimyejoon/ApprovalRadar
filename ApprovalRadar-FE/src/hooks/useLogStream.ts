import { useState, useEffect, useLayoutEffect, useRef, useCallback } from 'react';

export interface LogEntry {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | 'PING';
  message: string;
}

const MAX_LOGS = 500;
const envApiUrl = import.meta.env.VITE_API_URL;
const apiBaseUrl = envApiUrl !== undefined 
  ? (envApiUrl === '' ? window.location.origin : envApiUrl) 
  : 'http://localhost:8000';

const WS_URL = apiBaseUrl.replace(/^http/, 'ws') + '/api/v1/admin/logs';

export function useLogStream() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 언마운트 후 onclose 재연결 타이머 누수 방지:
  // cleanup이 실행된 후에도 onclose가 비동기로 발화하므로 flag로 차단
  const shouldReconnectRef = useRef(true);

  const connectRef = useRef<(() => void) | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    // 수동 연결 시 재연결 허용 상태로 복원
    shouldReconnectRef.current = true;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };

    ws.onmessage = (event) => {
      try {
        const entry: LogEntry = JSON.parse(event.data);
        if (entry.level === 'PING') return;
        setLogs(prev => {
          const next = [...prev, entry];
          return next.length > MAX_LOGS ? next.slice(next.length - MAX_LOGS) : next;
        });
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      // shouldReconnectRef가 false면 언마운트/의도적 종료 → 재연결 하지 않음
      if (shouldReconnectRef.current) {
        reconnectTimerRef.current = setTimeout(() => connectRef.current?.(), 5000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useLayoutEffect(() => {
    connectRef.current = connect;
  });

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
  }, []);

  useEffect(() => {
    connect();
    return () => {
      // 언마운트 시: 재연결 차단 후 close (onclose가 이후 발화해도 재연결 안 함)
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return { logs, isConnected, connect, disconnect, clearLogs };
}
