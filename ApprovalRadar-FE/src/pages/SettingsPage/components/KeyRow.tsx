import { useState } from 'react';
import { ToggleLeft, ToggleRight, Trash } from '@phosphor-icons/react';
import type { ApiKeyManagementItem } from '@/lib/api';
import { KeyStatusBadge } from './KeyStatusBadge';
import { UsageBar } from './UsageBar';
import { useUpdateApiKeyMemoMutation } from '../api';

interface KeyRowProps {
  item: ApiKeyManagementItem;
  onToggle: (id: number, is_active: boolean) => void;
  onDelete: (id: number, masked: string) => void;
  isUpdating: boolean;
  isDeleting: boolean;
}

export function KeyRow({ item, onToggle, onDelete, isUpdating, isDeleting }: KeyRowProps) {
  const [editMemo, setEditMemo] = useState(false);
  const [memoValue, setMemoValue] = useState(item.memo || '');
  const memoMutation = useUpdateApiKeyMemoMutation();

  const handleSaveMemo = () => {
    memoMutation.mutate(
      { id: item.id, memo: memoValue },
      {
        onSuccess: () => {
          setEditMemo(false);
        },
      }
    );
  };

  return (
    <tr className="border-b border-border-standard hover:bg-surface/50 transition-colors">
      {/* 인덱스 */}
      <td className="py-3 px-4 text-text-muted text-xs font-mono">#{item.id}</td>
      {/* 마스킹 키 */}
      <td className="py-3 px-4">
        <span className="font-mono text-sm text-text-primary tracking-wider">{item.key_masked}</span>
      </td>
      {/* 메모 */}
      <td className="py-3 px-4">
        {editMemo ? (
          <div className="flex items-center gap-2">
            <input
              className="text-xs px-2 py-1 rounded border border-brand/40 bg-surface text-text-primary focus:outline-none focus:border-brand w-40"
              value={memoValue}
              onChange={(e) => setMemoValue(e.target.value)}
              autoFocus
            />
            <button
              onClick={handleSaveMemo}
              disabled={memoMutation.isPending}
              className="text-brand text-xs hover:underline disabled:opacity-50"
            >
              {memoMutation.isPending ? '저장...' : '저장'}
            </button>
            <button
              onClick={() => {
                setEditMemo(false);
                setMemoValue(item.memo || '');
              }}
              disabled={memoMutation.isPending}
              className="text-text-muted text-xs hover:underline disabled:opacity-50"
            >
              취소
            </button>
          </div>
        ) : (
          <button
            onClick={() => setEditMemo(true)}
            className="text-xs text-text-muted hover:text-text-primary transition-colors text-left max-w-[160px] truncate"
            title="클릭하여 메모 수정"
          >
            {item.memo || <span className="italic text-text-muted/50">메모 없음</span>}
          </button>
        )}
      </td>
      {/* 오늘 사용량 */}
      <td className="py-3 px-4">
        <UsageBar used={item.call_count_today} />
      </td>
      {/* 상태 */}
      <td className="py-3 px-4">
        <KeyStatusBadge item={item} />
      </td>
      {/* 활성화 토글 */}
      <td className="py-3 px-4">
        <button
          onClick={() => onToggle(item.id, !item.is_active)}
          disabled={isUpdating}
          className="flex items-center gap-1.5 text-xs transition-colors disabled:opacity-50"
          title={item.is_active ? '비활성화' : '활성화'}
        >
          {item.is_active ? (
            <ToggleRight className="w-6 h-6 text-brand" weight="fill" />
          ) : (
            <ToggleLeft className="w-6 h-6 text-text-muted" />
          )}
        </button>
      </td>
      {/* 삭제 */}
      <td className="py-3 px-4">
        <button
          onClick={() => onDelete(item.id, item.key_masked)}
          disabled={isDeleting}
          className="p-1.5 rounded hover:bg-red-500/10 hover:text-red-400 text-text-muted transition-colors disabled:opacity-50"
          title="삭제"
        >
          <Trash className="w-4 h-4" />
        </button>
      </td>
    </tr>
  );
}
