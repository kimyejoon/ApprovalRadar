/**
 * 시스템 알림 팝업 이벤트 에미터 (비컴포넌트 로직만 분리)
 * SystemAlertPopup.tsx의 react-refresh/only-export-components 규칙 준수용
 */

export type SystemAlertType = 'WARN' | 'ALERT';

export interface SystemAlertItem {
  id: number;
  type: SystemAlertType;
  message: string;
}

type AlertListener = (item: SystemAlertItem) => void;

let _nextId = 1;
const _listeners: Set<AlertListener> = new Set();

/** 시스템 알림 팝업을 트리거합니다. 어디서든 import하여 사용 가능. */
export function emitSystemAlert(type: SystemAlertType, message: string) {
  const item: SystemAlertItem = { id: _nextId++, type, message };
  _listeners.forEach((fn) => fn(item));
}

/** 내부 전용: 팝업 컴포넌트에서 리스너를 등록/해제하기 위해 사용 */
export function _addAlertListener(fn: AlertListener) {
  _listeners.add(fn);
}

export function _removeAlertListener(fn: AlertListener) {
  _listeners.delete(fn);
}
