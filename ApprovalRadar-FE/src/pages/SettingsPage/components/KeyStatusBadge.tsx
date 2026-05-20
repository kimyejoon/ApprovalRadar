import { CheckCircle, XCircle } from '@phosphor-icons/react';
import type { ApiKeyManagementItem } from '@/lib/api';

export function KeyStatusBadge({ item }: { item: ApiKeyManagementItem }) {
  if (!item.is_active) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-surface border border-border-standard text-text-muted">
        비활성
      </span>
    );
  }
  if (item.is_exhausted) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/10 border border-yellow-500/30 text-yellow-400">
        <XCircle className="w-3 h-3" weight="fill" />
        소진
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-brand/10 border border-brand/30 text-brand">
      <CheckCircle className="w-3 h-3" weight="fill" />
      활성
    </span>
  );
}
