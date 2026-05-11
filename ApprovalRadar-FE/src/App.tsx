import { useState, useEffect, useMemo } from 'react';
import { DownloadSimple, CaretLeft, CaretRight, CaretUp, CaretDown, ArrowsDownUp, MagnifyingGlass, X } from '@phosphor-icons/react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { Button } from './components/ui/Button';
import { Modal } from './components/ui/Modal';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCodeCell } from './components/ui/Table';

function formatApprovalDate(dateStr: string) {
  if (!dateStr) return '-';
  
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;

  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');

  // Check if original string contains time information
  const hasTime = dateStr.includes('T') || /\s\d{2}:/.test(dateStr);
  
  if (hasTime) {
    return `${y}년 ${m}월 ${d}일 ${h}시 ${min}분`;
  }
  return `${y}년 ${m}월 ${d}일`;
}

// Dummy data
const INITIAL_DATA = [
  {
    id: 'TR-2026-001',
    name: '최고의 식당',
    type: '일반음식점',
    location: '서울특별시 강남구 테헤란로 123',
    owner: '홍길동',
    status: '영업/정상',
    approvalDate: '2026-05-11T14:30:00',
    phone: '02-1234-5678',
    isTransfer: true,
  },
  {
    id: 'TR-2026-002',
    name: '맛있는 베이커리',
    type: '제과점영업',
    location: '서울특별시 서초구 서초대로 456',
    owner: '김철수',
    status: '영업/정상',
    approvalDate: '2026-05-11',
    phone: '02-9876-5432',
    isTransfer: false,
  },
  {
    id: 'TR-2026-003',
    name: '조용한 카페',
    type: '휴게음식점',
    location: '서울특별시 송파구 올림픽로 789',
    owner: '이영희',
    status: '폐업',
    approvalDate: '2026-05-10T09:15:00',
    phone: '02-5555-4444',
    isTransfer: false,
  }
];

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
  const [data, setData] = useState(INITIAL_DATA);
  const [selectedItem, setSelectedItem] = useState<typeof INITIAL_DATA[0] | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('전체');
  const [isStatusFilterOpen, setIsStatusFilterOpen] = useState(false);

  const handleSort = (key: SortKey) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const filteredAndSortedData = useMemo(() => {
    let result = [...data];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(item => 
        item.name.toLowerCase().includes(query) ||
        item.owner.toLowerCase().includes(query) ||
        item.id.toLowerCase().includes(query)
      );
    }

    if (statusFilter !== '전체') {
      result = result.filter(item => item.status.includes(statusFilter));
    }

    if (sortConfig !== null) {
      result.sort((a, b) => {
        const { key, direction } = sortConfig;
        if (a[key] < b[key]) return direction === 'asc' ? -1 : 1;
        if (a[key] > b[key]) return direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return result;
  }, [data, sortConfig, searchQuery, statusFilter]);

  // Pagination logic
  const totalPages = Math.max(1, Math.ceil(filteredAndSortedData.length / itemsPerPage));
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedData = filteredAndSortedData.slice(startIndex, startIndex + itemsPerPage);

  // Simulate live data arriving (리스트 밀림 방식)
  useEffect(() => {
    const timer = setInterval(() => {
      const newItem = {
        id: `TR-2026-00${Math.floor(Math.random() * 10) + 4}`,
        name: '새로 수집된 식당 ' + Math.floor(Math.random() * 100),
        type: '일반음식점',
        location: '서울특별시 마포구 월드컵북로',
        owner: '박신규',
        status: '영업/정상',
        approvalDate: new Date().toISOString(),
        phone: `02-${Math.floor(Math.random() * 9000) + 1000}-${Math.floor(Math.random() * 9000) + 1000}`,
        isTransfer: Math.random() > 0.5,
      };
      
      // Add new item to the top of the list (리스트 밀림)
      setData(prev => [newItem, ...prev]);
    }, 15000); // 15 seconds for demo

    return () => clearInterval(timer);
  }, []);

  return (
    <DashboardLayout>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-sans font-medium text-text-primary tracking-tight">금일 변동 내역</h2>
          <p className="text-text-muted mt-1 text-sm">총 {data.length}건의 인허가 변동 데이터가 실시간으로 수집되고 있습니다.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => console.log('Export Excel')} className="gap-2">
            <DownloadSimple weight="bold" className="w-4 h-4" />
            엑셀 내보내기
          </Button>
        </div>
      </div>

      {/* Search Bar & Active Filters */}
      <div className="mb-6 flex flex-col gap-3">
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
        
        {/* Active Filters */}
        {statusFilter !== '전체' && (
          <div className="flex gap-2">
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
          </div>
        )}
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <SortableHead label="업소명" sortKey="name" sortConfig={sortConfig} onSort={handleSort} />
            <TableHead>소재지</TableHead>
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
          {paginatedData.map((item, index) => (
            <TableRow 
              key={item.id + index} 
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
          ))}
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
            총 {filteredAndSortedData.length}개 중 {filteredAndSortedData.length === 0 ? 0 : startIndex + 1}-{Math.min(startIndex + itemsPerPage, filteredAndSortedData.length)}
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
              <Button variant="primary">추가 작업</Button>
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
          <div className="pt-2 flex justify-end">
            <Button variant="primary" onClick={() => setIsStatusFilterOpen(false)}>적용 및 닫기</Button>
          </div>
        </div>
      </Modal>
    </DashboardLayout>
  );
}
