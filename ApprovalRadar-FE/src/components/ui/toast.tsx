import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, WarningCircle, Info, BellRinging } from '@phosphor-icons/react';
import type { Toast } from '@/store/useToastStore';
import { useToastStore } from '@/store/useToastStore';
import { cn } from '@/lib/utils';
import { Button } from './button';

interface ToastItemProps {
  toast: Toast;
}

const icons = {
  default: <BellRinging className="w-16 h-16 text-brand animate-pulse" weight="fill" />,
  success: <CheckCircle className="w-16 h-16 text-green-500" weight="fill" />,
  warning: <WarningCircle className="w-16 h-16 text-yellow-500" weight="fill" />,
  error: <WarningCircle className="w-16 h-16 text-red-500" weight="fill" />,
  info: <Info className="w-16 h-16 text-blue-500" weight="fill" />,
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
      className="relative bg-background border border-border-standard rounded-xl shadow-2xl w-full max-w-3xl flex flex-col overflow-hidden pointer-events-auto"
      role="alertdialog"
    >
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-standard shrink-0 bg-surface">
        <h2 className="text-lg font-sans font-medium text-text-primary m-0 tracking-tight flex items-center gap-2">
          <BellRinging className="w-5 h-5 text-brand" weight="fill" />
          실시간 중요 알림
        </h2>
        <Button variant="ghost" size="sm" className="w-8 h-8 p-0" onClick={() => removeToast(toast.id)} aria-label="Close">
          <X className="w-4 h-4 text-text-muted" />
        </Button>
      </div>

      <div className="flex flex-col md:flex-row items-center gap-8 p-10 bg-background">
        <div className="shrink-0">{icons[type]}</div>
        <div className="flex-1 flex flex-col gap-4 text-center md:text-left">
          <p className="text-3xl font-extrabold tracking-tight text-text-primary">{toast.title}</p>
          {toast.description && (
            <p className="text-2xl font-medium text-brand leading-snug">{toast.description}</p>
          )}
        </div>
      </div>
      
      <div className="px-6 py-4 border-t border-border-standard bg-surface flex justify-end">
         <Button onClick={() => removeToast(toast.id)} className="bg-brand text-white hover:bg-brand/90 transition-colors">
            확인 및 닫기
         </Button>
      </div>
    </motion.div>
  );
}

export function ToastProvider() {
  const toasts = useToastStore((state) => state.toasts);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed inset-0 z-100 flex items-center justify-center p-4 pointer-events-auto">
      <div className="absolute inset-0 bg-[rgba(15,15,15,0.84)] backdrop-blur-sm" />
      <div className="relative z-10 flex flex-col gap-4 w-full items-center">
        <AnimatePresence mode="popLayout">
          {toasts.map((toast) => (
            <ToastItem key={toast.id} toast={toast} />
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
