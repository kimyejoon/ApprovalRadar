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
      className="relative bg-background border border-border-standard rounded-2xl shadow-2xl w-full max-w-md flex flex-col overflow-hidden pointer-events-auto"
      role="alertdialog"
      aria-modal="true"
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border-standard shrink-0 bg-surface">
        <h2 className="text-sm font-sans font-semibold text-text-primary m-0 tracking-tight flex items-center gap-2">
          <BellRinging className={`w-4 h-4 ${accentClass} animate-pulse`} weight="fill" />
          실시간 변동 알림
        </h2>
        <div className="flex items-center gap-2.5">
          {/* 인디케이터 */}
          {totalNo > 1 && (
            <span className="text-[11px] font-mono text-text-muted bg-surface-secondary px-2 py-0.5 rounded-full border border-border-standard">
              {currentNo} / {totalNo}
            </span>
          )}
          {/* 닫기 */}
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center rounded-full hover:bg-surface-secondary text-text-muted hover:text-text-primary transition-colors"
            aria-label="닫기"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 본문 */}
      <div className="flex flex-col gap-4 p-5 bg-background">
        {/* 타이틀 & 설명 */}
        <div className="flex flex-col gap-1">
          <p className={`text-lg font-extrabold tracking-tight ${accentClass}`}>{toast.title}</p>
          {toast.description && (
            <p className="text-sm font-medium text-text-primary leading-snug">{toast.description}</p>
          )}
        </div>

        {/* 메타 그리드 */}
        {toast.metadata && toast.metadata.length > 0 && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 p-3 bg-surface-secondary/50 rounded-xl border border-border-standard">
            {toast.metadata.map((meta, idx) => (
              <div key={idx} className="flex flex-col">
                <span className="text-[10px] font-medium text-text-muted mb-0.5">{meta.label}</span>
                <span className="text-xs font-semibold text-text-primary break-keep">{meta.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 하단 액션 */}
      <div className="px-5 py-3 border-t border-border-standard bg-surface flex items-center justify-between gap-4">
        {/* 남은 알림 카운트 힌트 */}
        <span className="text-[11px] text-text-muted">
          {totalNo > 1
            ? `읽지 않은 알림 ${totalNo - 1}건 더 있음`
            : '모든 알림을 확인했습니다.'}
        </span>

        <div className="flex items-center gap-2">
          {/* 다음 / 닫기 버튼 */}
          {isLast ? (
            <button
              id="toast-close-btn"
              onClick={onClose}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-brand text-white text-xs font-semibold hover:bg-brand/90 transition-colors"
            >
              닫기
            </button>
          ) : (
            <button
              id="toast-next-btn"
              onClick={onNext}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-brand text-white text-xs font-semibold hover:bg-brand/90 transition-colors"
            >
              다음
              <CaretRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ─── Provider: 단일 팝업 렌더러 (우측 하단 토스트 형태) ─────────────────────────

export function ToastProvider() {
  const { toasts, currentIndex, next, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  const current = toasts[currentIndex] ?? toasts[0];

  return (
    <div className="fixed bottom-6 right-6 z-[100] p-4 pointer-events-auto w-full max-w-md flex flex-col items-end">
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
  );
}
