import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, startOfToday } from 'date-fns';
import { DownloadSimple, CaretLeft, CaretRight, CaretUp, CaretDown, ArrowsDownUp, MagnifyingGlass, X, ArrowCounterClockwise } from '@phosphor-icons/react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { Button } from './components/ui/button';
import { Modal } from './components/ui/Modal';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCodeCell } from './components/ui/Table';
import { KoreaMapSelector } from './components/ui/KoreaMapSelector';
import { DatePickerWithPresets } from './components/ui/DatePickerWithPresets';
import { DashboardIndicators } from './components/ui/DashboardIndicators';
import { fetchApprovals, type ApprovalData } from './lib/api';

const ALL_REGIONS = [
  '서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
  '대전광역시', '울산광역시', '세종특별자치시', '경기도', '강원도',
  '충청북도', '충청남도', '전라북도', '전라남도', '경상북도', '경상남도', '제주특별자치도'
];
const METRO_REGIONS = ['서울특별시', '인천광역시', '경기도', '강원도'];
const NON_METRO_REGIONS = ALL_REGIONS.filter(r => !METRO_REGIONS.includes(r));

function formatApprovalDate(dateStr: string) {
  if (!dateStr) return '-';
  
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;

  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');

  const hasTime = dateStr.includes('T') || /\s\d{2}:/.test(dateStr);
  
  if (hasTime) {
    return `${y}년 ${m}월 ${d}일 ${h}시 ${min}분`;
  }
  return `${y}년 ${m}월 ${d}일`;
}

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
  const [selectedItem, setSelectedItem] = useState<any>(null);
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

      <Modal 
        isOpen={!!selectedItem} 
        onClose={() => setSelectedItem(null)}
        title="인허가 변동 상세 내역"
      >
        {selectedItem && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-text-muted mb-1">업소명</div>
                <div className="font-medium text-text-primary">{selectedItem.name}</div>
              </div>
              <div>
                <div className="text-text-muted mb-1">인허가번호</div>
                <div className="font-mono text-text-primary">{selectedItem.id}</div>
              </div>
              <div className="col-span-2">
                <div className="text-text-muted mb-1">소재지</div>
                <div className="text-text-primary">{selectedItem.location}</div>
              </div>
              <div>
                <div className="text-text-muted mb-1">대표자명</div>
                <div className="text-text-primary">{selectedItem.owner}</div>
              </div>
              <div>
                <div className="text-text-muted mb-1">전화번호</div>
                <div className="font-mono text-text-primary">{selectedItem.phone}</div>
              </div>
              <div>
                <div className="text-text-muted mb-1">영업상태</div>
                <div className="text-text-primary">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    selectedItem.status.includes('정상') 
                      ? 'bg-brand/10 text-brand' 
                      : 'bg-border-prominent text-text-muted'
                  }`}>
                    {selectedItem.status}
                  </span>
                </div>
              </div>
              <div>
                <div className="text-text-muted mb-1">업종</div>
                <div className="text-text-primary">{selectedItem.type}</div>
              </div>
              <div className="col-span-2">
                <div className="text-text-muted mb-1">인허가시각</div>
                <div className="text-text-primary">{formatApprovalDate(selectedItem.approvalDate)}</div>
              </div>
            </div>
            
            <div className="pt-6 border-t border-border-standard flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setSelectedItem(null)}>닫기</Button>
              <Button variant="default">추가 작업</Button>
            </div>
          </div>
        )}
      </Modal>

      <Modal 
        isOpen={isStatusFilterOpen} 
        onClose={() => setIsStatusFilterOpen(false)}
        title="영업상태 필터"
      >
        <div className="space-y-4">
          <div className="flex flex-col gap-2">
            {['전체', '영업/정상', '폐업'].map(status => (
              <label 
                key={status} 
                className={`flex items-center gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-colors ${
                  statusFilter === status 
                    ? 'border-brand bg-brand/5' 
                    : 'border-border-standard hover:bg-border-subtle/50'
                }`}
              >
                <input 
                  type="radio" 
                  name="status_modal" 
                  value={status}
                  checked={statusFilter === status}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="accent-brand w-4 h-4"
                />
                <span className="text-sm font-medium text-text-primary">{status}</span>
              </label>
            ))}
          </div>
          <div className="flex justify-end mt-2">
            <Button variant="secondary" onClick={() => setIsStatusFilterOpen(false)}>닫기</Button>
          </div>
        </div>
      </Modal>

      {/* Location Filter Modal */}
      <Modal
        isOpen={isLocationFilterOpen}
        onClose={() => setIsLocationFilterOpen(false)}
        title="소재지 필터"
      >
        <div className="p-2 sm:p-4 flex flex-col items-center">
          <p className="text-sm text-text-muted mb-4 text-center">지도를 클릭하여 여러 지역을 선택할 수 있습니다.</p>
          
          {/* Quick Select Buttons */}
          <div className="flex flex-wrap justify-center gap-2 mb-4 w-full max-w-[500px]">
            <Button variant="secondary" onClick={() => setTempLocationFilters(METRO_REGIONS)} className="text-xs py-1 px-3">
              빠른선택: 수도권
            </Button>
            <Button variant="secondary" onClick={() => setTempLocationFilters(NON_METRO_REGIONS)} className="text-xs py-1 px-3">
              수도권 외
            </Button>
            <Button variant="secondary" onClick={() => setTempLocationFilters(ALL_REGIONS)} className="text-xs py-1 px-3">
              전국 선택
            </Button>
            <Button variant="secondary" onClick={() => setTempLocationFilters([])} className="text-xs py-1 px-3 flex items-center gap-1 text-text-muted hover:text-text-primary transition-colors">
              <ArrowCounterClockwise weight="bold" className="w-3.5 h-3.5" />
              초기화
            </Button>
          </div>
          
          {/* Selected Location Tags in Modal */}
          {tempLocationFilters.length > 0 && (
            <div className="flex flex-wrap justify-center gap-2 mb-4 w-full max-w-[500px]">
              {tempLocationFilters.map(loc => (
                <span key={loc} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand/10 text-brand text-xs font-medium border border-brand/20 shadow-sm transition-all">
                  {loc}
                  <button 
                    onClick={() => setTempLocationFilters(prev => prev.filter(l => l !== loc))}
                    className="hover:bg-brand/20 rounded-full p-0.5 transition-colors focus:outline-none flex items-center justify-center"
                  >
                    <X weight="bold" className="w-3.5 h-3.5" />
                  </button>
                </span>
              ))}
            </div>
          )}

          <KoreaMapSelector 
            selectedLocations={tempLocationFilters} 
            onSelect={(locations) => {
              setTempLocationFilters(locations);
            }} 
          />
          <div className="flex justify-end gap-2 mt-6 w-full max-w-[500px]">
            <Button variant="secondary" onClick={() => setIsLocationFilterOpen(false)}>취소</Button>
            <Button variant="default" onClick={() => {
              setLocationFilters(tempLocationFilters);
              setCurrentPage(1);
              setIsLocationFilterOpen(false);
            }}>적용</Button>
          </div>
        </div>
      </Modal>
    </DashboardLayout>
  );
}
