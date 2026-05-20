import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Plus, Eye, EyeSlash, Play } from '@phosphor-icons/react';
import { createApiKey } from '@/lib/api';

export function AddKeyForm({ onSuccess }: { onSuccess: () => void }) {
  const [keyValue, setKeyValue] = useState('');
  const [memo, setMemo] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [resumedMsg, setResumedMsg] = useState<'resumed' | 'invalid' | null>(null);

  const mutation = useMutation({
    mutationFn: () => createApiKey(keyValue.trim(), memo.trim() || undefined),
    onSuccess: (data) => {
      setKeyValue('');
      setMemo('');
      setErrorMsg('');
      if (data.crawl_resumed) {
        setResumedMsg('resumed');
      } else if (data.is_active && !data.is_exhausted) {
        setResumedMsg(null);
      }
      onSuccess();
    },
    onError: (e: Error) => { setErrorMsg(e.message); setResumedMsg(null); },
  });

  return (
    <div className="bg-surface/40 border border-border-standard rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-medium text-text-primary flex items-center gap-2">
        <Plus className="w-4 h-4 text-brand" />
        새 API 키 등록
      </h3>
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <input
            id="new-api-key-input"
            type={showKey ? 'text' : 'password'}
            placeholder="식품안전나라 API 키 입력..."
            value={keyValue}
            onChange={(e) => setKeyValue(e.target.value)}
            className="w-full px-3 py-2 pr-9 rounded-lg border border-border-standard bg-surface text-sm text-text-primary focus:outline-none focus:border-brand/60 font-mono"
          />
          <button
            type="button"
            onClick={() => setShowKey(!showKey)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
          >
            {showKey ? <EyeSlash className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        <input
          id="new-api-key-memo"
          type="text"
          placeholder="메모 (선택)"
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          className="w-48 px-3 py-2 rounded-lg border border-border-standard bg-surface text-sm text-text-primary focus:outline-none focus:border-brand/60"
        />
        <button
          id="add-api-key-btn"
          onClick={() => mutation.mutate()}
          disabled={!keyValue.trim() || mutation.isPending}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
        >
          <Plus className="w-4 h-4" />
          {mutation.isPending ? '등록 중...' : '등록'}
        </button>
      </div>
      {errorMsg && <p className="text-xs text-red-400">{errorMsg}</p>}

      {resumedMsg === 'resumed' && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-brand/10 border border-brand/30 text-brand text-xs font-medium">
          <Play className="w-3.5 h-3.5" weight="fill" />
          새 키 검증 통과 — 크롤링이 즉시 재개됩니다.
        </div>
      )}
    </div>
  );
}
