import { useState, useEffect } from 'react';
import { DownloadSimple } from '@phosphor-icons/react';
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

export default function App() {
  const [data, setData] = useState(INITIAL_DATA);
  const [selectedItem, setSelectedItem] = useState<typeof INITIAL_DATA[0] | null>(null);

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

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>업소명</TableHead>
            <TableHead>소재지</TableHead>
            <TableHead>인허가번호</TableHead>
            <TableHead>대표자명</TableHead>
            <TableHead>영업상태</TableHead>
            <TableHead>인허가시각</TableHead>
            <TableHead>전화번호</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((item, index) => (
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
    </DashboardLayout>
  );
}
