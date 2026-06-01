import { useMemo, useState } from 'react';
import { CaretDown, CaretUp, ArrowsDownUp, Copy, Check } from '@phosphor-icons/react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCodeCell } from '@/components/ui/Table';
import { formatApprovalDate, formatIndexedAt } from '@/lib/utils';
import type { ApprovalMappedItem } from '@/lib/api';
import type { SortKey } from '@/hooks/useApprovalRadar';
import { CATEGORY_COLORS, CATEGORY_ICONS, INDUSTRY_ICONS } from '@/lib/constants';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="p-1 rounded-full hover:bg-border-subtle active:bg-border-standard transition-all flex items-center justify-center border border-border-standard text-text-muted hover:text-brand focus:outline-none w-6 h-6 shrink-0 ml-1.5"
      title="복사하기"
    >
      {copied ? (
        <Check weight="bold" className="w-3.5 h-3.5 text-emerald-500" />
      ) : (
        <Copy weight="bold" className="w-3.5 h-3.5" />
      )}
    </button>
  );
}

interface SortableHeadProps {
  label: string;
  sortKey: SortKey;
  sortConfig: { key: SortKey; direction: 'asc' | 'desc' } | null;
  onSort: (key: SortKey) => void;
}

function SortableHead({ label, sortKey, sortConfig, onSort }: SortableHeadProps) {
  const isActive = sortConfig?.key === sortKey;
  return (
    <TableHead>
      <button
        onClick={() => onSort(sortKey)}
        className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
      >
        {label}
        <span className="text-text-muted flex items-center justify-center w-4 h-4">
          {isActive ? (
            sortConfig.direction === 'asc' ? <CaretUp weight="bold" /> : <CaretDown weight="bold" />
          ) : (
            <ArrowsDownUp />
          )}
        </span>
      </button>
    </TableHead>
  );
}

interface ApprovalTableProps {
  data: ApprovalMappedItem[];
  isLoading: boolean;
  isError: boolean;
  sortConfig: { key: SortKey; direction: 'asc' | 'desc' } | null;
  onSort: (key: SortKey) => void;
  onRowClick: (item: ApprovalMappedItem) => void;
  onLocationClick: () => void;
  onStatusClick: () => void;
  onIndustryClick: () => void;
  mode?: 'changes' | 'new';
}

export function ApprovalTable({
  data,
  isLoading,
  isError,
  sortConfig,
  onSort,
  onRowClick,
  onLocationClick,
  onStatusClick,
  onIndustryClick,
  mode = 'changes',
}: ApprovalTableProps) {
  // 같은 (license_no, last_event_date) 를 하나의 그룹으로 묶음
  // 여러 변경 유형이 동날짜에 발생하면 1개 행으로 표시하되 태그를 복수 표시
  const groupedRows = useMemo(() => {
    const groups = new Map<string, ApprovalMappedItem[]>();
    for (const item of data) {
      const key = `${item.raw.license_no}__${item.raw.last_event_date}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(item);
    }
    return Array.from(groups.values());
  }, [data]);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableHead label="업소명" sortKey="name" sortConfig={sortConfig} onSort={onSort} />
          <SortableHead label="인허가번호" sortKey="id" sortConfig={sortConfig} onSort={onSort} />
          <TableHead>
            <button
              className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
              onClick={onLocationClick}
            >
              소재지
              <CaretDown weight="bold" className="w-4 h-4" />
            </button>
          </TableHead>
          <SortableHead label="대표자명" sortKey="owner" sortConfig={sortConfig} onSort={onSort} />
          <TableHead>
            <button
              className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
              onClick={onIndustryClick}
            >
              업종
              <CaretDown weight="bold" className="w-4 h-4" />
            </button>
          </TableHead>
          <TableHead>
            {mode === 'new' ? (
              <span className="flex items-center gap-1 text-text-muted font-medium text-xs">
                구분
              </span>
            ) : (
              <button
                className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
                onClick={onStatusClick}
              >
                변경 타입
                <CaretDown weight="bold" className="w-4 h-4" />
              </button>
            )}
          </TableHead>
          <SortableHead label={mode === 'new' ? '인허가 일자' : '인허가 변동시각'} sortKey="approvalDate" sortConfig={sortConfig} onSort={onSort} />
          <SortableHead label="전화번호" sortKey="phone" sortConfig={sortConfig} onSort={onSort} />
        </TableRow>
      </TableHeader>
      <TableBody>
        {isLoading ? (
          <TableRow>
            <TableCell colSpan={8} className="text-center py-8 text-text-muted">데이터를 불러오는 중입니다...</TableCell>
          </TableRow>
        ) : isError ? (
          <TableRow>
            <TableCell colSpan={8} className="text-center py-8 text-text-muted">데이터를 불러오는데 실패했습니다.</TableCell>
          </TableRow>
        ) : groupedRows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={8} className="text-center py-8 text-text-muted">검색 결과가 없습니다.</TableCell>
          </TableRow>
        ) : (
          groupedRows.map((group, index) => {
            // 대표 아이템(모달 열 때 사용) — 가장 의미있는 변경 우선
            const PRIORITY = ['대표자변경', '상태변경', '변경민원-상호명', '명칭변경'];
            const primaryItem = group.reduce((best, cur) => {
              const bp = PRIORITY.indexOf(best.raw.infer_update_type || '');
              const cp = PRIORITY.indexOf(cur.raw.infer_update_type || '');
              return (cp !== -1 && (bp === -1 || cp < bp)) ? cur : best;
            }, group[0]);

            // 중복 없는 타입 목록 (순서 유지)
            const seen = new Set<string>();
            const typeEntries = group
              .map(g => ({ type: g.raw.infer_update_type || '', detail: g.updateDetail || '' }))
              .filter(t => { if (seen.has(t.type)) return false; seen.add(t.type); return true; });

            const isUnread = group.some(g => !g.isRead);

            return (
              <TableRow
                key={`${primaryItem.raw.license_no}-${primaryItem.raw.last_event_date}-${index}`}
                className={isUnread ? 'bg-emerald-400/20 hover:bg-emerald-400/30' : ''}
              >
                <TableCell className="font-medium text-text-primary">
                  <div className="flex items-center gap-1.5 justify-between">
                    <div
                      onClick={() => onRowClick(primaryItem)}
                      className="flex flex-col cursor-pointer hover:underline hover:text-brand transition-colors"
                    >
                      <span className="text-[15px] font-bold text-text-primary leading-tight">{primaryItem.name}</span>
                      {primaryItem.prevName && (
                        <span className="text-xs text-brand/80 mt-0.5 leading-tight break-keep">
                          (이전: {primaryItem.prevName})
                        </span>
                      )}
                    </div>
                    <CopyButton text={primaryItem.name} />
                  </div>
                </TableCell>
                <TableCodeCell>
                  <div className="flex items-center gap-1.5 justify-between">
                    <span className="text-[15px] font-semibold text-text-primary font-mono">{primaryItem.id}</span>
                    <CopyButton text={primaryItem.id} />
                  </div>
                </TableCodeCell>
                <TableCell className="whitespace-nowrap">
                  <div className="flex items-center gap-1.5 justify-between">
                    <span className="text-[15px] font-medium text-text-primary">{primaryItem.location}</span>
                    <CopyButton text={primaryItem.location} />
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex flex-col">
                    <span>{primaryItem.owner}</span>
                    {primaryItem.prevOwner && (
                      <span className="text-[11px] text-brand mt-0.5 leading-tight break-keep">
                        (이전: {primaryItem.prevOwner})
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="text-sm text-text-muted">
                  <div className="flex items-center gap-1.5">
                    {INDUSTRY_ICONS[primaryItem.type] && (
                      <span className="flex items-center text-text-secondary">
                        {(() => {
                          const Icon = INDUSTRY_ICONS[primaryItem.type];
                          return <Icon weight="regular" size={14} />;
                        })()}
                      </span>
                    )}
                    <span>{primaryItem.type}</span>
                  </div>
                </TableCell>
                <TableCell>
                  {/* 변경 타입: 같은 날 여러 타입이면 태그 복수 표시 */}
                  <div className="flex flex-col items-start gap-1">
                    {typeEntries.map((entry, ti) => (
                      <div key={ti} className="flex flex-col items-start gap-0.5">
                        <span
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-sm font-bold text-white border"
                          style={{
                            backgroundColor: CATEGORY_COLORS[entry.type] || '#9ca3af',
                            borderColor: CATEGORY_COLORS[entry.type] || '#9ca3af',
                          }}
                        >
                          {CATEGORY_ICONS[entry.type] && (
                            <span className="flex items-center text-white">
                              {(() => {
                                const Icon = CATEGORY_ICONS[entry.type];
                                return <Icon weight="bold" size={13} />;
                              })()}
                            </span>
                          )}
                          {entry.type || '-'}
                        </span>
                        {entry.detail && (
                          <span className="text-sm font-bold text-text-primary mt-1.5 ml-0.5 leading-snug break-words block">
                            {entry.detail}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="text-xs text-text-muted">
                  <div className="flex flex-col gap-0.5">
                    <span>{formatApprovalDate(primaryItem.approvalDate)}</span>
                    {primaryItem.raw.created_at && (
                      <span className="text-[10px] text-text-muted/60 leading-tight">
                        색인일: {formatIndexedAt(primaryItem.raw.created_at)}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell className="font-mono text-xs">{primaryItem.phone}</TableCell>
              </TableRow>
            );
          })
        )}
      </TableBody>
    </Table>
  );
}
