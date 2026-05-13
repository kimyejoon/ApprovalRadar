import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, WarningCircle, Info, BellRinging } from '@phosphor-icons/react';
import type { Toast } from '@/store/useToastStore';
import { useToastStore } from '@/store/useToastStore';
import { cn } from '@/lib/utils';

interface ToastItemProps {
  toast: Toast;
}

const icons = {
  default: <BellRinging className="w-14 h-14 text-brand animate-pulse" weight="fill" />,
  success: <CheckCircle className="w-14 h-14 text-green-500" weight="fill" />,
  warning: <WarningCircle className="w-14 h-14 text-yellow-500" weight="fill" />,
  error: <WarningCircle className="w-14 h-14 text-red-500" weight="fill" />,
  info: <Info className="w-14 h-14 text-blue-500" weight="fill" />,
};

const bgColors = {
  default: 'bg-surface-primary border-brand/50 shadow-brand/20',
  success: 'bg-surface-primary border-green-500/50 shadow-green-500/20',
  warning: 'bg-surface-primary border-yellow-500/50 shadow-yellow-500/20',
  error: 'bg-surface-primary border-red-500/50 shadow-red-500/20',
  info: 'bg-surface-primary border-blue-500/50 shadow-blue-500/20',
};

export function ToastItem({ toast }: ToastItemProps) {
  const removeToast = useToastStore((state) => state.removeToast);
  const type = toast.type || 'default';

  return (
    <motion.div
      initial={{ opacity: 0, y: 50, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
      layout
      className={cn(
        'pointer-events-auto flex w-full max-w-4xl rounded-3xl border-4 p-8 shadow-2xl',
        bgColors[type]
      )}
    >
      <div className="flex w-full items-start gap-8">
        <div className="shrink-0 mt-1">{icons[type]}</div>
        <div className="flex-1 flex flex-col gap-4">
          <p className="text-4xl font-extrabold tracking-tight text-text-primary">{toast.title}</p>
          {toast.description && (
            <p className="text-2xl font-medium text-text-secondary leading-snug">{toast.description}</p>
          )}
        </div>
        <button
          onClick={() => removeToast(toast.id)}
          className="shrink-0 rounded-2xl p-4 text-text-muted hover:bg-surface-secondary hover:text-text-primary transition-colors focus:outline-none focus:ring-4 focus:ring-brand/50"
        >
          <X className="w-10 h-10" weight="bold" />
        </button>
      </div>
    </motion.div>
  );
}

export function ToastProvider() {
  const toasts = useToastStore((state) => state.toasts);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed inset-0 z-100 flex max-h-screen w-full flex-col items-center justify-center gap-6 p-8 pointer-events-auto bg-black/60 backdrop-blur-md transition-all duration-300">
      <AnimatePresence mode="popLayout">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} />
        ))}
      </AnimatePresence>
    </div>
  );
}
