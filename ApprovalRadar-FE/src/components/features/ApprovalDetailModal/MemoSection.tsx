import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PencilSimple, Trash, Plus, Check, X, NotePencil } from '@phosphor-icons/react';
import { fetchMemo, createMemo, updateMemo, deleteMemo } from '../../../lib/api';

const MAX_MEMO_LENGTH = 500;

interface MemoSectionProps {
  licenseDate: string;
  businessName: string;
}

export function MemoSection({ licenseDate, businessName }: MemoSectionProps) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<'view' | 'create' | 'edit'>('view');
  const [inputValue, setInputValue] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const memoKey = ['memo', licenseDate, businessName];

  const { data: memoResp, isLoading } = useQuery({
    queryKey: memoKey,
    queryFn: () => fetchMemo({ license_date: licenseDate, business_name: businessName }),
    enabled: !!licenseDate && !!businessName,
  });

  const memo = memoResp?.data ?? null;

  const invalidate = () => queryClient.invalidateQueries({ queryKey: memoKey });

  const createMutation = useMutation({
    mutationFn: (content: string) =>
      createMemo({ license_date: licenseDate, business_name: businessName, content }),
    onSuccess: () => { setMode('view'); setErrorMsg(''); invalidate(); },
    onError: (e: Error) => setErrorMsg(e.message),
  });

  const updateMutation = useMutation({
    mutationFn: (content: string) =>
      updateMemo({ license_date: licenseDate, business_name: businessName, content }),
    onSuccess: () => { setMode('view'); setErrorMsg(''); invalidate(); },
    onError: (e: Error) => setErrorMsg(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteMemo({ license_date: licenseDate, business_name: businessName }),
    onSuccess: () => { setIsDeleting(false); setMode('view'); invalidate(); },
    onError: (e: Error) => setErrorMsg(e.message),
  });

  const handleOpenCreate = () => {
    setInputValue('');
    setErrorMsg('');
    setMode('create');
  };

  const handleOpenEdit = () => {
    setInputValue(memo?.content ?? '');
    setErrorMsg('');
    setMode('edit');
  };

  const handleCancel = () => {
    setMode('view');
    setInputValue('');
    setErrorMsg('');
    setIsDeleting(false);
  };

  const handleSave = () => {
    const trimmed = inputValue.trim();
    if (!trimmed) { setErrorMsg('메모 내용을 입력해주세요.'); return; }
    if (trimmed.length > MAX_MEMO_LENGTH) { setErrorMsg(`최대 ${MAX_MEMO_LENGTH}자까지 입력 가능합니다.`); return; }
    if (mode === 'create') createMutation.mutate(trimmed);
    else updateMutation.mutate(trimmed);
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="bg-surface border border-border-standard rounded-lg p-4 space-y-3">
      {/* 섹션 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold text-text-secondary">
          <NotePencil weight="duotone" size={16} className="text-brand" />
          <span>메모</span>
        </div>
        {mode === 'view' && !memo && !isLoading && (
          <button
            id="memo-add-btn"
            onClick={handleOpenCreate}
            className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand/80 transition-colors"
          >
            <Plus weight="bold" size={12} />
            메모 추가
          </button>
        )}
        {mode === 'view' && memo && (
          <div className="flex items-center gap-2">
            <button
              id="memo-edit-btn"
              onClick={handleOpenEdit}
              className="inline-flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text-secondary transition-colors"
            >
              <PencilSimple weight="bold" size={12} />
              수정
            </button>
            {!isDeleting ? (
              <button
                id="memo-delete-btn"
                onClick={() => setIsDeleting(true)}
                className="inline-flex items-center gap-1 text-xs font-medium text-red-400 hover:text-red-300 transition-colors"
              >
                <Trash weight="bold" size={12} />
                삭제
              </button>
            ) : (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-text-muted">삭제하시겠어요?</span>
                <button
                  id="memo-delete-confirm-btn"
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                  className="inline-flex items-center gap-0.5 text-xs font-medium text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                >
                  <Check weight="bold" size={11} />
                  확인
                </button>
                <button
                  onClick={handleCancel}
                  className="inline-flex items-center gap-0.5 text-xs font-medium text-text-muted hover:text-text-secondary transition-colors"
                >
                  <X weight="bold" size={11} />
                  취소
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 콘텐츠 영역 */}
      {isLoading ? (
        <div className="text-xs text-text-muted py-1">불러오는 중...</div>
      ) : mode === 'view' && memo ? (
        <div className="space-y-1">
          <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap wrap-break-words">
            {memo.content}
          </p>
          <p className="text-[11px] text-text-muted">
            {memo.updated_at !== memo.created_at ? `수정됨 · ` : `작성됨 · `}
            {new Date(memo.updated_at).toLocaleString('ko-KR', {
              year: 'numeric', month: '2-digit', day: '2-digit',
              hour: '2-digit', minute: '2-digit',
            })}
          </p>
        </div>
      ) : mode === 'view' && !memo ? (
        <div className="text-xs text-text-muted py-1">
          아직 작성된 메모가 없습니다. 위의 <span className="text-brand font-medium">메모 추가</span>를 눌러 기록을 남겨보세요.
        </div>
      ) : (mode === 'create' || mode === 'edit') ? (
        <div className="space-y-2">
          <textarea
            id="memo-textarea"
            value={inputValue}
            onChange={(e) => { setInputValue(e.target.value); setErrorMsg(''); }}
            placeholder="이 인허가 건에 대한 메모를 입력하세요..."
            maxLength={MAX_MEMO_LENGTH}
            rows={4}
            className="w-full resize-none rounded-md border border-border-standard bg-background px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-brand focus:border-brand transition-colors"
          />
          <div className="flex items-center justify-between">
            <div className="flex flex-col gap-0.5">
              {errorMsg && (
                <span className="text-xs text-red-400">{errorMsg}</span>
              )}
              <span className="text-[11px] text-text-muted">
                {inputValue.length} / {MAX_MEMO_LENGTH}자
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCancel}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium text-text-muted hover:text-text-secondary hover:bg-surface transition-colors border border-border-standard"
              >
                <X weight="bold" size={11} />
                취소
              </button>
              <button
                id="memo-save-btn"
                onClick={handleSave}
                disabled={isSaving}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium bg-brand text-white hover:bg-brand/90 transition-colors disabled:opacity-50"
              >
                <Check weight="bold" size={11} />
                {isSaving ? '저장 중...' : '저장'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
