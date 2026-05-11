import { useState, useEffect } from 'react';
import { DownloadSimple } from '@phosphor-icons/react';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { Button } from './components/ui/Button';
import { Modal } from './components/ui/Modal';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCodeCell } from './components/ui/Table';

// Dummy data
const INITIAL_DATA = [
  {
    id: 'TR-2026-001',
    name: '최고의 식당',
    type: '일반음식점',
    location: '서울특별시 강남구 테헤란로 123',
    owner: '홍길동',
    date: '2026-05-11',
    status: '영업/정상',
    isTransfer: true,
  },
  {
    id: 'TR-2026-002',
    name: '맛있는 베이커리',
    type: '제과점영업',
    location: '서울특별시 서초구 서초대로 456',
    owner: '김철수',
    date: '2026-05-11',
    status: '영업/정상',
    isTransfer: false,
  },
  {
    id: 'TR-2026-003',
    name: '조용한 카페',
    type: '휴게음식점',
    location: '서울특별시 송파구 올림픽로 789',
    owner: '이영희',
    date: '2026-05-10',
    status: '폐업',
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
        date: new Date().toISOString().split('T')[0],
        status: '영업/정상',
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
            <TableHead>인허가번호</TableHead>
            <TableHead>업소명</TableHead>
            <TableHead>업종</TableHead>
            <TableHead>소재지</TableHead>
            <TableHead>대표자</TableHead>
            <TableHead>처리일자</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((item, index) => (
            <TableRow 
              key={item.id + index} 
              onClick={() => setSelectedItem(item)}
              className="cursor-pointer group"
            >
              <TableCodeCell>{item.id}</TableCodeCell>
              <TableCell className="font-medium text-text-primary group-hover:text-brand transition-colors">
                {item.name}
              </TableCell>
              <TableCell>{item.type}</TableCell>
              <TableCell className="max-w-[200px] truncate">{item.location}</TableCell>
              <TableCell>{item.owner}</TableCell>
              <TableCell>{item.date}</TableCell>
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
                <div className="text-text-muted mb-1">인허가번호</div>
                <div className="font-mono text-text-primary">{selectedItem.id}</div>
              </div>
              <div>
                <div className="text-text-muted mb-1">업소명</div>
                <div className="font-medium text-text-primary">{selectedItem.name}</div>
              </div>
              <div>
                <div className="text-text-muted mb-1">업종</div>
                <div className="text-text-primary">{selectedItem.type}</div>
              </div>
              <div>
                <div className="text-text-muted mb-1">영업상태</div>
                <div className="text-text-primary">{selectedItem.status}</div>
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
                <div className="text-text-muted mb-1">처리일자</div>
                <div className="text-text-primary">{selectedItem.date}</div>
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
