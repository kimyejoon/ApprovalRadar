import { CaretDown, CaretUp, ArrowsDownUp } from '@phosphor-icons/react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCodeCell } from '@/components/ui/Table';
import { formatApprovalDate } from '@/lib/utils';
import type { ApprovalMappedItem } from '@/lib/api';
import type { SortKey } from '@/hooks/useApprovalRadar';

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
}: ApprovalTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableHead label="업소명" sortKey="name" sortConfig={sortConfig} onSort={onSort} />
          <TableHead>
            <button 
              className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
              onClick={onLocationClick}
            >
              소재지
              <CaretDown weight="bold" className="w-4 h-4" />
            </button>
          </TableHead>
          <SortableHead label="인허가번호" sortKey="id" sortConfig={sortConfig} onSort={onSort} />
          <SortableHead label="대표자명" sortKey="owner" sortConfig={sortConfig} onSort={onSort} />
          <TableHead>
            <button 
              className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
              onClick={onStatusClick}
            >
              영업상태
              <CaretDown weight="bold" className="w-4 h-4" />
            </button>
          </TableHead>
          <SortableHead label="인허가 변동시각" sortKey="approvalDate" sortConfig={sortConfig} onSort={onSort} />
          <SortableHead label="전화번호" sortKey="phone" sortConfig={sortConfig} onSort={onSort} />
        </TableRow>
      </TableHeader>
      <TableBody>
        {isLoading ? (
          <TableRow>
            <TableCell colSpan={7} className="text-center py-8 text-text-muted">데이터를 불러오는 중입니다...</TableCell>
          </TableRow>
        ) : isError ? (
          <TableRow>
            <TableCell colSpan={7} className="text-center py-8 text-text-muted">데이터를 불러오는데 실패했습니다.</TableCell>
          </TableRow>
        ) : data.length === 0 ? (
          <TableRow>
            <TableCell colSpan={7} className="text-center py-8 text-text-muted">검색 결과가 없습니다.</TableCell>
          </TableRow>
        ) : (
          data.map((item, index) => (
            <TableRow 
              key={item.id + '-' + index} 
              onClick={() => onRowClick(item)}
              className="cursor-pointer group"
            >
              <TableCell className="font-medium text-text-primary group-hover:text-brand transition-colors">
                {item.name}
              </TableCell>
              <TableCell>{item.location}</TableCell>
              <TableCodeCell>{item.id}</TableCodeCell>
              <TableCell>{item.owner}</TableCell>
              <TableCell>
                <span className={`px-2 py-1 rounded text-xs font-medium ${
                  item.status.includes('정상') || item.status.includes('영업') 
                    ? 'bg-brand/10 text-brand' 
                    : 'bg-border-prominent text-text-muted'
                }`}>
                  {item.status}
                </span>
              </TableCell>
              <TableCell className="text-xs text-text-muted">{formatApprovalDate(item.approvalDate)}</TableCell>
              <TableCell className="font-mono text-xs">{item.phone}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
