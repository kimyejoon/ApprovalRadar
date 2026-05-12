import { MagnifyingGlass, X } from '@phosphor-icons/react';
import { DatePickerWithPresets } from '@/components/ui/DatePickerWithPresets';

interface DashboardFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  dateRange: { from?: Date; to?: Date } | undefined;
  onDateRangeChange: (range: { from?: Date; to?: Date } | undefined) => void;
  statusFilter: string;
  onStatusReset: () => void;
  locationFilters: string[];
  onLocationRemove: (location: string) => void;
}

export function DashboardFilters({
  searchQuery,
  onSearchChange,
  dateRange,
  onDateRangeChange,
  statusFilter,
  onStatusReset,
  locationFilters,
  onLocationRemove,
}: DashboardFiltersProps) {
  return (
    <>
      {/* Search Bar & Date Picker */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center bg-surface border border-border-standard rounded-lg px-3 py-2 w-full max-w-md focus-within:ring-1 focus-within:ring-brand focus-within:border-brand transition-all shadow-sm">
          <MagnifyingGlass className="w-5 h-5 text-text-muted mr-2" />
          <input 
            type="text" 
            placeholder="업소명, 대표자명, 인허가번호 검색..." 
            className="bg-transparent border-none outline-none text-text-primary text-sm w-full placeholder:text-text-muted"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
        
        {/* Date Filter */}
        <DatePickerWithPresets date={dateRange} setDate={onDateRangeChange} />
      </div>

      {/* Active Filters Row */}
      {(statusFilter !== '전체' || locationFilters.length > 0) && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {statusFilter !== '전체' && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand/10 text-brand text-xs font-medium border border-brand/20 shadow-sm">
              영업상태: {statusFilter}
              <button 
                onClick={onStatusReset}
                className="hover:bg-brand/20 rounded-full p-0.5 transition-colors focus:outline-none flex items-center justify-center"
              >
                <X weight="bold" className="w-3.5 h-3.5" />
              </button>
            </span>
          )}
          
          {locationFilters.map(loc => (
            <span key={loc} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand/10 text-brand text-xs font-medium border border-brand/20 shadow-sm">
              소재지: {loc}
              <button 
                onClick={() => onLocationRemove(loc)}
                className="hover:bg-brand/20 rounded-full p-0.5 transition-colors focus:outline-none flex items-center justify-center"
              >
                <X weight="bold" className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </>
  );
}
