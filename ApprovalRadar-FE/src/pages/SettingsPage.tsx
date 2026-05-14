import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Key,
  Plus,
  Trash,
  ArrowsClockwise,
  CheckCircle,
  XCircle,
  ToggleLeft,
  ToggleRight,
  Eye,
  EyeSlash,
} from '@phosphor-icons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  fetchApiKeys,
  createApiKey,
  updateApiKey,
  deleteApiKey,
  type ApiKeyManagementItem,
} from '@/lib/api';

// ─── 상태 배지 컴포넌트 ────────────────────────────────────────────────────

function KeyStatusBadge({ item }: { item: ApiKeyManagementItem }) {
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

// ─── 사용량 바 컴포넌트 ────────────────────────────────────────────────────

function UsageBar({ used, limit = 1000 }: { used: number; limit?: number }) {
  const pct = Math.min((used / limit) * 100, 100);
  const color = pct >= 90 ? 'bg-red-500' : pct >= 60 ? 'bg-yellow-400' : 'bg-brand';
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="flex-1 h-1.5 rounded-full bg-surface-secondary overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-text-muted font-mono whitespace-nowrap">
        {used.toLocaleString()} / {limit.toLocaleString()}
      </span>
    </div>
  );
}

// ─── 키 행 컴포넌트 ────────────────────────────────────────────────────────

interface KeyRowProps {
  item: ApiKeyManagementItem;
  onToggle: (id: number, is_active: boolean) => void;
  onDelete: (id: number, masked: string) => void;
  isUpdating: boolean;
  isDeleting: boolean;
}

function KeyRow({ item, onToggle, onDelete, isUpdating, isDeleting }: KeyRowProps) {
  const [editMemo, setEditMemo] = useState(false);
  const [memoValue, setMemoValue] = useState(item.memo || '');
  const queryClient = useQueryClient();

  const memoMutation = useMutation({
    mutationFn: (memo: string) => updateApiKey(item.id, { memo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings-api-keys'] });
      setEditMemo(false);
    },
  });

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
              onClick={() => memoMutation.mutate(memoValue)}
              className="text-brand text-xs hover:underline"
            >저장</button>
            <button
              onClick={() => { setEditMemo(false); setMemoValue(item.memo || ''); }}
              className="text-text-muted text-xs hover:underline"
            >취소</button>
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

// ─── 키 추가 폼 ────────────────────────────────────────────────────────────

function AddKeyForm({ onSuccess }: { onSuccess: () => void }) {
  const [keyValue, setKeyValue] = useState('');
  const [memo, setMemo] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const mutation = useMutation({
    mutationFn: () => createApiKey(keyValue.trim(), memo.trim() || undefined),
    onSuccess: () => {
      setKeyValue('');
      setMemo('');
      setErrorMsg('');
      onSuccess();
    },
    onError: (e: Error) => setErrorMsg(e.message),
  });

  return (
    <div className="bg-surface-secondary/40 border border-border-standard rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-medium text-text-primary flex items-center gap-2">
        <Plus className="w-4 h-4 text-brand" />
        새 API 키 등록
      </h3>
      <div className="flex flex-col sm:flex-row gap-3">
        {/* 키 입력 */}
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
        {/* 메모 */}
        <input
          id="new-api-key-memo"
          type="text"
          placeholder="메모 (선택)"
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          className="w-48 px-3 py-2 rounded-lg border border-border-standard bg-surface text-sm text-text-primary focus:outline-none focus:border-brand/60"
        />
        {/* 등록 버튼 */}
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
    </div>
  );
}

// ─── 메인 설정 페이지 ──────────────────────────────────────────────────────

export function SettingsPage() {
  const queryClient = useQueryClient();

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['settings-api-keys'],
    queryFn: fetchApiKeys,
    refetchInterval: 60_000,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      updateApiKey(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings-api-keys'] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteApiKey(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings-api-keys'] }),
  });

  const handleDelete = (id: number, masked: string) => {
    if (!window.confirm(`${masked} 키를 삭제할까요?\n삭제 후 복구가 불가합니다.`)) return;
    deleteMutation.mutate(id);
  };

  const activeCount = data?.keys.filter((k) => k.is_active && !k.is_exhausted).length ?? 0;
  const exhaustedCount = data?.keys.filter((k) => k.is_exhausted).length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      {/* 페이지 헤더 */}
      <div>
        <p className="text-sm text-text-muted mt-1">
          식품안전나라 API 키를 DB에서 관리합니다. 변경 사항은 서버 재시작 없이 즉시 반영됩니다.
        </p>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="border-border-standard bg-surface-primary">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-text-muted flex items-center gap-2">
              <Key className="w-4 h-4" />전체 키
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-text-primary">{data?.total ?? '-'}</div>
          </CardContent>
        </Card>
        <Card className="border-border-standard bg-surface-primary">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-text-muted flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-brand" />활성 키
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-brand">{activeCount}</div>
          </CardContent>
        </Card>
        <Card className="border-border-standard bg-surface-primary">
          <CardHeader className="pb-1">
            <CardTitle className="text-sm font-medium text-text-muted flex items-center gap-2">
              <XCircle className="w-4 h-4 text-yellow-400" />소진 키
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-yellow-400">{exhaustedCount}</div>
          </CardContent>
        </Card>
      </div>

      {/* API 키 관리 카드 */}
      <Card className="border-border-standard bg-surface-primary">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Key className="w-4 h-4 text-brand" />
              API 키 목록
            </span>
            <button
              onClick={() => refetch()}
              className="text-text-muted hover:text-text-primary transition-colors"
              title="새로고침"
            >
              <ArrowsClockwise className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            </button>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* 키 추가 폼 */}
          <AddKeyForm onSuccess={() => queryClient.invalidateQueries({ queryKey: ['settings-api-keys'] })} />

          {/* 키 테이블 */}
          <div className="overflow-x-auto rounded-xl border border-border-standard">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-standard bg-surface">
                  <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted">ID</th>
                  <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted">키 (마스킹)</th>
                  <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted">메모</th>
                  <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted">오늘 호출 / 한도</th>
                  <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted">상태</th>
                  <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted">활성화</th>
                  <th className="py-2.5 px-4 text-left text-xs font-medium text-text-muted">삭제</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-text-muted text-xs">
                      키 목록을 불러오는 중...
                    </td>
                  </tr>
                ) : !data?.keys.length ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-text-muted text-xs">
                      등록된 API 키가 없습니다. 위 폼에서 키를 추가하세요.
                    </td>
                  </tr>
                ) : (
                  data.keys.map((item) => (
                    <KeyRow
                      key={item.id}
                      item={item}
                      onToggle={(id, is_active) => toggleMutation.mutate({ id, is_active })}
                      onDelete={handleDelete}
                      isUpdating={toggleMutation.isPending}
                      isDeleting={deleteMutation.isPending}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-text-muted">
            * 오늘 호출 한도는 식품안전나라 기준 키당 1,000회입니다. 소진된 키는 자정 이후 자동 초기화됩니다.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
