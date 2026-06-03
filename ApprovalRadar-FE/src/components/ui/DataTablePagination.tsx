import { Button } from '@/components/ui/button';
import { CaretLeft, CaretRight } from '@phosphor-icons/react';

interface DataTablePaginationProps {
  itemsPerPage: number;
  totalCount: number;
  currentPage: number;
  totalPages: number;
  onItemsPerPageChange: (value: number) => void;
  onPageChange: (page: number) => void;
}

export function DataTablePagination({
  itemsPerPage,
  totalCount,
  currentPage,
  totalPages,
  onItemsPerPageChange,
  onPageChange
}: DataTablePaginationProps) {
  const startIndex = (currentPage - 1) * itemsPerPage;

  return (
    <div className="mt-4 flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        <span className="text-text-muted">페이지당 행:</span>
        <select 
          className="bg-surface border border-border-standard rounded-md px-2 py-1 text-text-primary focus:outline-none focus:ring-1 focus:ring-brand"
          value={itemsPerPage}
          onChange={(e) => onItemsPerPageChange(Number(e.target.value))}
        >
          <option value={50}>50</option>
          <option value={100}>100</option>
          <option value={200}>200</option>
        </select>
      </div>
      
      <div className="flex items-center gap-4">
        <span className="text-text-muted">
          총 {totalCount.toLocaleString()}개 중 {totalCount === 0 ? 0 : (startIndex + 1).toLocaleString()}-{Math.min(startIndex + itemsPerPage, totalCount).toLocaleString()}
        </span>
        <div className="flex items-center gap-1">
          <Button 
            variant="ghost" 
            size="sm" 
            className="w-8 h-8 p-0 disabled:opacity-30" 
            disabled={currentPage === 1}
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          >
            <CaretLeft weight="bold" className="w-4 h-4" />
          </Button>
          <Button 
            variant="ghost" 
            size="sm" 
            className="w-8 h-8 p-0 disabled:opacity-30" 
            disabled={currentPage === totalPages || totalPages === 0}
            onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          >
            <CaretRight weight="bold" className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
