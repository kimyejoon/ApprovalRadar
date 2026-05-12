import { create } from 'zustand';

interface IndicatorState {
  todayNewCount: number;
  setTodayNewCount: (count: number) => void;
}

export const useIndicatorStore = create<IndicatorState>((set) => ({
  todayNewCount: 0,
  setTodayNewCount: (count) => set({ todayNewCount: count }),
}));
