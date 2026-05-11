import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, startOfToday } from 'date-fns';
import { DownloadSimple, CaretLeft, CaretRight, CaretUp, CaretDown, ArrowsDownUp, MagnifyingGlass, X } from '@phosphor-icons/react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { Button } from './components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCodeCell } from './components/ui/Table';
import { DatePickerWithPresets } from './components/ui/DatePickerWithPresets';
import { DashboardIndicators } from './components/ui/DashboardIndicators';
import { fetchApprovals, type ApprovalData, type ApprovalMappedItem } from './lib/api';
import { formatApprovalDate } from './lib/utils';
import { ApprovalDetailModal } from './components/features/ApprovalDetailModal';
import { StatusFilterModal } from './components/features/StatusFilterModal';
import { LocationFilterModal } from './components/features/LocationFilterModal';

type SortKey = 'name' | 'owner' | 'approvalDate' | 'phone' | 'id';

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

export default function App() {
  const [selectedItem, setSelectedItem] = useState<ApprovalMappedItem | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('전체');
  const [locationFilters, setLocationFilters] = useState<string[]>([]);
  const [tempLocationFilters, setTempLocationFilters] = useState<string[]>([]);
  const [isStatusFilterOpen, setIsStatusFilterOpen] = useState(false);
  const [isLocationFilterOpen, setIsLocationFilterOpen] = useState(false);
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | undefined>({
    from: startOfToday(),
    to: startOfToday()
  });

  const { data: apiResponse, isLoading, isError } = useQuery({
    queryKey: ['approvals', currentPage, itemsPerPage, searchQuery, statusFilter, locationFilters, dateRange, sortConfig],
    queryFn: () => fetchApprovals({
      page: currentPage,
      size: itemsPerPage,
      search: searchQuery.trim() || undefined,
      start_date: dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined,
      end_date: dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined,
      regions: locationFilters.length > 0 ? locationFilters.join(',') : undefined,
      statuses: statusFilter !== '전체' ? statusFilter : undefined,
      sort_by: sortConfig ? (
        sortConfig.key === 'id' ? 'license_no' :
        sortConfig.key === 'name' ? 'business_name' :
        sortConfig.key === 'owner' ? 'representative_name' :
        sortConfig.key === 'approvalDate' ? 'license_date' :
        sortConfig.key === 'phone' ? 'phone_number' : 'created_at'
      ) : 'created_at',
      sort_order: sortConfig ? sortConfig.direction : 'desc',
    }),
    refetchInterval: 1000 * 60 * 5, // 5 min polling
    refetchOnWindowFocus: true,
  });

  const mappedData = apiResponse?.data.map((item: ApprovalData) => ({
    id: item.license_no,
    name: item.business_name,
    type: '-', // 업종 필드 부재
    location: item.address,
    owner: item.representative_name,
    status: item.business_status,
    approvalDate: item.license_date,
    phone: item.phone_number,
    isTransfer: false,
    raw: item,
  })) || [];

  const totalPages = apiResponse?.meta.total_pages || 1;
  const totalCount = apiResponse?.meta.total_count || 0;
  const startIndex = (currentPage - 1) * itemsPerPage;

  const handleSort = (key: SortKey) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  return (
    <DashboardLayout>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-sans font-medium text-text-primary tracking-tight">금일 변동 내역</h2>
          <p className="text-text-muted mt-1 text-sm">총 {totalCount}건의 인허가 변동 데이터가 실시간으로 수집되고 있습니다.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => console.log('Export Excel')} className="gap-2">
            <DownloadSimple weight="bold" className="w-4 h-4" />
            엑셀 내보내기
          </Button>
        </div>
      </div>

      {/* Dashboard Top Indicators */}
      <DashboardIndicators data={mappedData} />

      {/* Search Bar & Date Picker */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center bg-surface border border-border-standard rounded-lg px-3 py-2 w-full max-w-md focus-within:ring-1 focus-within:ring-brand focus-within:border-brand transition-all shadow-sm">
          <MagnifyingGlass className="w-5 h-5 text-text-muted mr-2" />
          <input 
            type="text" 
            placeholder="업소명, 대표자명, 인허가번호 검색..." 
            className="bg-transparent border-none outline-none text-text-primary text-sm w-full placeholder:text-text-muted"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
          />
        </div>
        
        {/* Date Filter */}
        <DatePickerWithPresets date={dateRange} setDate={(newDate) => { setDateRange(newDate); setCurrentPage(1); }} />
      </div>

      {/* Active Filters Row */}
      {(statusFilter !== '전체' || locationFilters.length > 0) && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {statusFilter !== '전체' && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand/10 text-brand text-xs font-medium border border-brand/20 shadow-sm">
              영업상태: {statusFilter}
              <button 
                onClick={() => {
                  setStatusFilter('전체');
                  setCurrentPage(1);
                }}
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
                onClick={() => {
                  setLocationFilters(prev => prev.filter(l => l !== loc));
                  setCurrentPage(1);
                }}
                className="hover:bg-brand/20 rounded-full p-0.5 transition-colors focus:outline-none flex items-center justify-center"
              >
                <X weight="bold" className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <SortableHead label="업소명" sortKey="name" sortConfig={sortConfig} onSort={handleSort} />
            <TableHead>
              <button 
                className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
                onClick={() => {
                  setTempLocationFilters(locationFilters);
                  setIsLocationFilterOpen(true);
                }}
              >
                소재지
                <CaretDown weight="bold" className="w-4 h-4" />
              </button>
            </TableHead>
            <SortableHead label="인허가번호" sortKey="id" sortConfig={sortConfig} onSort={handleSort} />
            <SortableHead label="대표자명" sortKey="owner" sortConfig={sortConfig} onSort={handleSort} />
            <TableHead>
              <button 
                className="flex items-center gap-1 hover:text-text-primary transition-colors focus:outline-none"
                onClick={() => setIsStatusFilterOpen(true)}
              >
                영업상태
                <CaretDown weight="bold" className="w-4 h-4" />
              </button>
            </TableHead>
            <SortableHead label="인허가시각" sortKey="approvalDate" sortConfig={sortConfig} onSort={handleSort} />
            <SortableHead label="전화번호" sortKey="phone" sortConfig={sortConfig} onSort={handleSort} />
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
          ) : mappedData.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center py-8 text-text-muted">검색 결과가 없습니다.</TableCell>
            </TableRow>
          ) : (
            mappedData.map((item, index) => (
              <TableRow 
                key={item.id + '-' + index} 
                onClick={() => setSelectedItem(item)}
                className="cursor-pointer group"
              >
                <TableCell className="font-medium text-text-primary group-hover:text-brand transition-colors">
                  {item.name}
                </TableCell>
                <TableCell className="max-w-[200px] truncate">{item.location}</TableCell>
                <TableCodeCell>{item.id}</TableCodeCell>
                <TableCell>{item.owner}</TableCell>
                <TableCell>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    item.status.includes('정상') 
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

      <div className="mt-4 flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <span className="text-text-muted">페이지당 행:</span>
          <select 
            className="bg-surface border border-border-standard rounded-md px-2 py-1 text-text-primary focus:outline-none focus:ring-1 focus:ring-brand"
            value={itemsPerPage}
            onChange={(e) => {
              setItemsPerPage(Number(e.target.value));
              setCurrentPage(1);
            }}
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>
        </div>
        
        <div className="flex items-center gap-4">
          <span className="text-text-muted">
            총 {totalCount}개 중 {totalCount === 0 ? 0 : startIndex + 1}-{Math.min(startIndex + itemsPerPage, totalCount)}
          </span>
          <div className="flex items-center gap-1">
            <Button 
              variant="ghost" 
              size="sm" 
              className="w-8 h-8 p-0 disabled:opacity-30" 
              disabled={currentPage === 1}
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            >
              <CaretLeft weight="bold" className="w-4 h-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="sm" 
              className="w-8 h-8 p-0 disabled:opacity-30" 
              disabled={currentPage === totalPages || totalPages === 0}
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            >
              <CaretRight weight="bold" className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      <ApprovalDetailModal 
        isOpen={!!selectedItem} 
        onClose={() => setSelectedItem(null)} 
        selectedItem={selectedItem} 
      />

      <StatusFilterModal 
        isOpen={isStatusFilterOpen} 
        onClose={() => setIsStatusFilterOpen(false)} 
        statusFilter={statusFilter} 
        setStatusFilter={setStatusFilter} 
        onFilterChange={() => setCurrentPage(1)} 
      />

      <LocationFilterModal 
        isOpen={isLocationFilterOpen} 
        onClose={() => setIsLocationFilterOpen(false)} 
        tempLocationFilters={tempLocationFilters} 
        setTempLocationFilters={setTempLocationFilters} 
        onApply={() => {
          setLocationFilters(tempLocationFilters);
          setCurrentPage(1);
          setIsLocationFilterOpen(false);
        }} 
      />
    </DashboardLayout>
  );
}
