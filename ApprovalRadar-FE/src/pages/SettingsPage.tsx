import { useQueryClient } from '@tanstack/react-query';
import { Key, ArrowsClockwise } from '@phosphor-icons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// 분리한 API 및 서브 컴포넌트 임포트
import { useApiKeysQuery, useToggleApiKeyMutation, useDeleteApiKeyMutation } from './SettingsPage/api';
import { KeyRow } from './SettingsPage/components/KeyRow';
import { AddKeyForm } from './SettingsPage/components/AddKeyForm';
import { NotificationSection } from './SettingsPage/components/NotificationSection';

export function SettingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isFetching, refetch } = useApiKeysQuery();
  const toggleMutation = useToggleApiKeyMutation();
  const deleteMutation = useDeleteApiKeyMutation();

  const handleDelete = (id: number, masked: string) => {
    if (!window.confirm(`${masked} 키를 삭제할까요?\n삭제 후 복구가 불가합니다.`)) return;
    deleteMutation.mutate(id);
  };

  return (
    <div className="flex flex-col gap-6">
      {/* 페이지 헤더 */}
      <div>
        <p className="text-sm text-text-muted mt-1">
          식품안전나라 API 키를 DB에서 관리합니다. 변경 사항은 서버 재시작 없이 즉시 반영됩니다.
        </p>
      </div>

      {/* API 키 관리 카드 */}
      <Card className="border-border-standard bg-surface">
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

      {/* 알림 설정 카드 */}
      <NotificationSection />
    </div>
  );
}
export default SettingsPage;
