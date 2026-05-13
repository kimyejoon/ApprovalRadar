import { MagnifyingGlass, X } from '@phosphor-icons/react';
import { DatePickerWithPresets } from '@/components/ui/DatePickerWithPresets';
import { CATEGORY_NAMES, CATEGORY_ICONS } from '@/lib/constants';

const ALL_REGIONS = [
  '서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
  '대전광역시', '울산광역시', '세종특별자치시', '경기도', '강원도',
  '충청북도', '충청남도', '전라북도', '전라남도', '경상북도', '경상남도', '제주특별자치도'
];
const METRO_REGIONS = ['서울특별시', '인천광역시', '경기도', '강원도'];
const NON_METRO_REGIONS = ALL_REGIONS.filter(r => !METRO_REGIONS.includes(r));

const arrayEquals = (a: string[], b: string[]) => {
  if (a.length !== b.length) return false;
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((val, index) => val === sortedB[index]);
};

interface DashboardFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  dateRange: { from?: Date; to?: Date } | undefined;
  onDateRangeChange: (range: { from?: Date; to?: Date } | undefined) => void;
  statusFilter: string;
  onStatusReset: () => void;
  locationFilters: string[];
  onLocationFiltersChange: (locations: string[]) => void;
}

export function DashboardFilters({
  searchQuery,
  onSearchChange,
  dateRange,
  onDateRangeChange,
  statusFilter,
  onStatusReset,
  locationFilters,
  onLocationFiltersChange,
}: DashboardFiltersProps) {
  let groupedTags: { label: string, onRemove: () => void }[] = [];

  if (locationFilters.length > 0) {
    if (arrayEquals(locationFilters, ALL_REGIONS)) {
      groupedTags.push({ label: '전국', onRemove: () => onLocationFiltersChange([]) });
    } else if (arrayEquals(locationFilters, METRO_REGIONS)) {
      groupedTags.push({ label: '수도권', onRemove: () => onLocationFiltersChange([]) });
    } else if (arrayEquals(locationFilters, NON_METRO_REGIONS)) {
      groupedTags.push({ label: '수도권 외', onRemove: () => onLocationFiltersChange([]) });
    } else {
      groupedTags = locationFilters.map(loc => ({
        label: loc,
        onRemove: () => onLocationFiltersChange(locationFilters.filter(l => l !== loc))
      }));
    }
  }

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
      {(statusFilter !== '전체' || groupedTags.length > 0) && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {statusFilter !== '전체' && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand/10 text-brand text-xs font-medium border border-brand/20 shadow-sm">
              {CATEGORY_ICONS[statusFilter] && (
                <span className="flex items-center">
                  {(() => {
                    const Icon = CATEGORY_ICONS[statusFilter];
                    return <Icon weight="bold" size={14} />;
                  })()}
                </span>
              )}
              변경 타입: {CATEGORY_NAMES[statusFilter] || statusFilter}
              <button 
                onClick={onStatusReset}
                className="hover:bg-brand/20 rounded-full p-0.5 transition-colors focus:outline-none flex items-center justify-center"
              >
                <X weight="bold" className="w-3.5 h-3.5" />
              </button>
            </span>
          )}
          
          {groupedTags.map(tag => (
            <span key={tag.label} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand/10 text-brand text-xs font-medium border border-brand/20 shadow-sm">
              소재지: {tag.label}
              <button 
                onClick={tag.onRemove}
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
