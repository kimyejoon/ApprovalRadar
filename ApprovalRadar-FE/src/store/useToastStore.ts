import { create } from 'zustand';

export interface Toast {
  id: string;
  title: string;
  description?: string;
  type?: 'default' | 'success' | 'warning' | 'error' | 'info';
  duration?: number;
  metadata?: Array<{ label: string; value: string }>;
}

interface ToastState {
  toasts: Toast[];
  currentIndex: number;
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
  removeAll: () => void;
  next: () => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  currentIndex: 0,

  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9);
    set((state) => ({
      toasts: [...state.toasts, { ...toast, id }],
      // 첫 번째 알림이 도착하면 currentIndex는 0 유지, 이후 추가는 뒤에 쌓임
    }));

    // duration이 명시적 숫자(>0)이면 자동 제거 (duration: 0이면 수동 닫기)
    if (toast.duration !== undefined && toast.duration !== 0) {
      setTimeout(() => {
        set((state) => {
          const toasts = state.toasts.filter((t) => t.id !== id);
          const currentIndex = Math.min(state.currentIndex, Math.max(0, toasts.length - 1));
          return { toasts, currentIndex };
        });
      }, toast.duration || 5000);
    }
  },

  removeToast: (id) =>
    set((state) => {
      const toasts = state.toasts.filter((t) => t.id !== id);
      const currentIndex = Math.min(state.currentIndex, Math.max(0, toasts.length - 1));
      return { toasts, currentIndex };
    }),

  removeAll: () => set({ toasts: [], currentIndex: 0 }),

  next: () =>
    set((state) => {
      if (state.currentIndex < state.toasts.length - 1) {
        // 현재 알림을 제거하고 다음으로 이동 (항상 인덱스 0 유지)
        const toasts = state.toasts.filter((_, i) => i !== state.currentIndex);
        return { toasts, currentIndex: 0 };
      }
      // 마지막 알림이면 모두 닫기
      return { toasts: [], currentIndex: 0 };
    }),
}));
