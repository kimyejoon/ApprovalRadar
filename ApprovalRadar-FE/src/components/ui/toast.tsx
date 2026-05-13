import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, WarningCircle, Info, BellRinging } from '@phosphor-icons/react';
import type { Toast } from '@/store/useToastStore';
import { useToastStore } from '@/store/useToastStore';
import { cn } from '@/lib/utils';

interface ToastItemProps {
  toast: Toast;
}

const icons = {
  default: <BellRinging className="w-5 h-5 text-brand animate-pulse" weight="fill" />,
  success: <CheckCircle className="w-5 h-5 text-green-500" weight="fill" />,
  warning: <WarningCircle className="w-5 h-5 text-yellow-500" weight="fill" />,
  error: <WarningCircle className="w-5 h-5 text-red-500" weight="fill" />,
  info: <Info className="w-5 h-5 text-blue-500" weight="fill" />,
};

const bgColors = {
  default: 'bg-surface-primary border-brand/30 shadow-brand/10',
  success: 'bg-surface-primary border-green-500/30 shadow-green-500/10',
  warning: 'bg-surface-primary border-yellow-500/30 shadow-yellow-500/10',
  error: 'bg-surface-primary border-red-500/30 shadow-red-500/10',
  info: 'bg-surface-primary border-blue-500/30 shadow-blue-500/10',
};

export function ToastItem({ toast }: ToastItemProps) {
  const removeToast = useToastStore((state) => state.removeToast);
  const type = toast.type || 'default';

  return (
    <motion.div
      initial={{ opacity: 0, y: 50, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
      layout
      className={cn(
        'pointer-events-auto flex w-full max-w-md rounded-xl border p-4 shadow-lg backdrop-blur-sm',
        bgColors[type]
      )}
    >
      <div className="flex w-full items-start gap-4">
        <div className="shrink-0 mt-0.5">{icons[type]}</div>
        <div className="flex-1 flex flex-col gap-1">
          <p className="text-sm font-semibold text-text-primary">{toast.title}</p>
          {toast.description && (
            <p className="text-sm text-text-secondary leading-relaxed">{toast.description}</p>
          )}
        </div>
        <button
          onClick={() => removeToast(toast.id)}
          className="shrink-0 rounded-lg p-1 text-text-muted hover:bg-surface-secondary hover:text-text-primary transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </motion.div>
  );
}

export function ToastProvider() {
  const toasts = useToastStore((state) => state.toasts);

  return (
    <div className="fixed inset-0 z-100 flex max-h-screen w-full flex-col items-center justify-center gap-3 p-4 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} />
        ))}
      </AnimatePresence>
    </div>
  );
}
