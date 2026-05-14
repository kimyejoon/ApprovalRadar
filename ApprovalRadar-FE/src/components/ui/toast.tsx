import { motion, AnimatePresence } from 'framer-motion';
import { BellRinging, CaretRight, X } from '@phosphor-icons/react';
import type { Toast } from '@/store/useToastStore';
import { useToastStore } from '@/store/useToastStore';

// ─── 아이콘 맵 (type별) ──────────────────────────────────────────────────────
const TYPE_ACCENT: Record<string, string> = {
  default: 'text-brand',
  success: 'text-green-400',
  warning: 'text-yellow-400',
  error:   'text-red-400',
  info:    'text-blue-400',
};

// ─── 단일 토스트 콘텐츠 ─────────────────────────────────────────────────────

interface ToastItemProps {
  toast: Toast;
  currentNo: number;   // 1-based 현재 번호
  totalNo: number;     // 전체 알림 수
  onNext: () => void;
  onClose: () => void;
}

export function ToastItem({ toast, currentNo, totalNo, onNext, onClose }: ToastItemProps) {
  const type = toast.type || 'default';
  const accentClass = TYPE_ACCENT[type] ?? TYPE_ACCENT.default;
  const isLast = currentNo >= totalNo;

  return (
    <motion.div
      key={toast.id}
      initial={{ opacity: 0, y: 40, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.94, transition: { duration: 0.18 } }}
      layout
      className="relative bg-background border border-border-standard rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col overflow-hidden pointer-events-auto"
      role="alertdialog"
      aria-modal="true"
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-standard shrink-0 bg-surface">
        <h2 className="text-base font-sans font-semibold text-text-primary m-0 tracking-tight flex items-center gap-2">
          <BellRinging className={`w-5 h-5 ${accentClass} animate-pulse`} weight="fill" />
          실시간 변동 알림
        </h2>
        <div className="flex items-center gap-3">
          {/* 인디케이터 */}
          {totalNo > 1 && (
            <span className="text-xs font-mono text-text-muted bg-surface-secondary px-2.5 py-1 rounded-full border border-border-standard">
              {currentNo} / {totalNo}
            </span>
          )}
          {/* 닫기 */}
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-surface-secondary text-text-muted hover:text-text-primary transition-colors"
            aria-label="닫기"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 본문 */}
      <div className="flex flex-col gap-5 p-8 bg-background">
        {/* 타이틀 & 설명 */}
        <div className="flex flex-col gap-2">
          <p className={`text-2xl font-extrabold tracking-tight ${accentClass}`}>{toast.title}</p>
          {toast.description && (
            <p className="text-lg font-medium text-text-primary leading-snug">{toast.description}</p>
          )}
        </div>

        {/* 메타 그리드 */}
        {toast.metadata && toast.metadata.length > 0 && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 p-4 bg-surface-secondary/50 rounded-xl border border-border-standard">
            {toast.metadata.map((meta, idx) => (
              <div key={idx} className="flex flex-col">
                <span className="text-xs font-medium text-text-muted mb-0.5">{meta.label}</span>
                <span className="text-sm font-semibold text-text-primary break-keep">{meta.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 하단 액션 */}
      <div className="px-6 py-4 border-t border-border-standard bg-surface flex items-center justify-between gap-4">
        {/* 남은 알림 카운트 힌트 */}
        <span className="text-xs text-text-muted">
          {totalNo > 1
            ? `읽지 않은 알림 ${totalNo - 1}건이 더 있습니다.`
            : '모든 알림을 확인했습니다.'}
        </span>

        <div className="flex items-center gap-2">
          {/* 다음 / 닫기 버튼 */}
          {isLast ? (
            <button
              id="toast-close-btn"
              onClick={onClose}
              className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-brand text-white text-sm font-semibold hover:bg-brand/90 transition-colors"
            >
              닫기
            </button>
          ) : (
            <button
              id="toast-next-btn"
              onClick={onNext}
              className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-brand text-white text-sm font-semibold hover:bg-brand/90 transition-colors"
            >
              다음
              <CaretRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ─── Provider: 단일 팝업 렌더러 ─────────────────────────────────────────────

export function ToastProvider() {
  const { toasts, currentIndex, next, removeToast, removeAll } = useToastStore();

  if (toasts.length === 0) return null;

  const current = toasts[currentIndex] ?? toasts[0];

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 pointer-events-auto">
      {/* 배경 오버레이 */}
      <div
        className="absolute inset-0 bg-[rgba(10,10,10,0.80)] backdrop-blur-sm"
        onClick={removeAll}
      />
      {/* 단일 토스트 */}
      <div className="relative z-10 w-full flex justify-center">
        <AnimatePresence mode="wait">
          <ToastItem
            key={current.id}
            toast={current}
            currentNo={currentIndex + 1}
            totalNo={toasts.length}
            onNext={next}
            onClose={() => removeToast(current.id)}
          />
        </AnimatePresence>
      </div>
    </div>
  );
}
