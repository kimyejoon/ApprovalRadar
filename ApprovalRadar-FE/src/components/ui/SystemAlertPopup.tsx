import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Warning, XCircle, X } from '@phosphor-icons/react';
import {
  _addAlertListener,
  _removeAlertListener,
} from '@/lib/systemAlertEmitter';
import type { SystemAlertItem } from '@/lib/systemAlertEmitter';

// ─── 팝업 큐 훅 ───────────────────────────────────────────────────────────

function useSystemAlertQueue() {
  const [queue, setQueue] = useState<SystemAlertItem[]>([]);

  useEffect(() => {
    const listener = (item: SystemAlertItem) => {
      setQueue((prev) => [...prev, item]);
      setTimeout(() => {
        setQueue((prev) => prev.filter((a) => a.id !== item.id));
      }, 7000);
    };
    _addAlertListener(listener);
    return () => { _removeAlertListener(listener); };
  }, []);

  const dismiss = (id: number) => setQueue((prev) => prev.filter((a) => a.id !== id));

  return { queue, dismiss };
}

// ─── 개별 팝업 카드 ───────────────────────────────────────────────────────

function AlertPopupCard({
  item,
  onDismiss,
}: {
  item: SystemAlertItem;
  onDismiss: () => void;
}) {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    const start = Date.now();
    const duration = 7000;
    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - start;
      const remaining = Math.max(0, 100 - (elapsed / duration) * 100);
      setProgress(remaining);
      if (remaining <= 0) {
        if (timerRef.current) clearInterval(timerRef.current);
        onDismiss();
      }
    }, 50);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [onDismiss]);

  const isWarn = item.type === 'WARN';

  const styles = isWarn
    ? {
        border: 'border-yellow-500/40',
        bg: 'bg-yellow-500/10',
        icon: <Warning className="w-4 h-4 text-yellow-400 shrink-0" weight="fill" />,
        bar: 'bg-yellow-400',
        label: 'text-yellow-300',
        labelText: '⚠ 경고',
      }
    : {
        border: 'border-red-500/50',
        bg: 'bg-red-500/10',
        icon: <XCircle className="w-4 h-4 text-red-400 shrink-0" weight="fill" />,
        bar: 'bg-red-500',
        label: 'text-red-300',
        labelText: '🚨 오류',
      };

  return (
    <motion.div
      initial={{ x: 80, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 80, opacity: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      className={`relative w-80 rounded-xl border ${styles.border} ${styles.bg} backdrop-blur-sm shadow-xl overflow-hidden`}
    >
      {/* 프로그레스 바 */}
      <div className="absolute top-0 left-0 h-[2px] w-full bg-white/10">
        <div
          className={`h-full ${styles.bar} transition-none`}
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="flex items-start gap-3 p-4 pt-5">
        {styles.icon}
        <div className="flex-1 min-w-0">
          <p className={`text-xs font-bold mb-0.5 ${styles.label}`}>{styles.labelText}</p>
          <p className="text-xs text-text-secondary leading-relaxed overflow-wrap-break-word">{item.message}</p>
        </div>
        <button
          onClick={onDismiss}
          className="text-text-muted hover:text-text-primary transition-colors shrink-0 mt-0.5"
          title="닫기"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </motion.div>
  );
}

// ─── 팝업 컨테이너 (App에 마운트) ──────────────────────────────────────────

export function SystemAlertPopup() {
  const { queue, dismiss } = useSystemAlertQueue();

  return (
    <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-2 items-end pointer-events-none">
      <AnimatePresence mode="sync">
        {queue.map((item) => (
          <div key={item.id} className="pointer-events-auto">
            <AlertPopupCard item={item} onDismiss={() => dismiss(item.id)} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  );
}
