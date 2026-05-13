import { useQuery } from '@tanstack/react-query';
import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { formatApprovalDate } from '../../lib/utils';
import { type ApprovalMappedItem, fetchApprovalDetail } from '../../lib/api';
import { CATEGORY_COLORS, CATEGORY_ICONS, INDUSTRY_ICONS } from '@/lib/constants';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';

interface ApprovalDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedItem: ApprovalMappedItem | null;
}

export function ApprovalDetailModal({ isOpen, onClose, selectedItem }: ApprovalDetailModalProps) {
  const { data: detailResponse, isLoading, isError } = useQuery({
    queryKey: ['approvalDetail', selectedItem?.raw.license_date, selectedItem?.name],
    queryFn: () => {
      if (!selectedItem?.raw.license_date || !selectedItem?.name) {
        return Promise.reject(new Error('Missing required parameters'));
      }
      return fetchApprovalDetail({
        license_date: selectedItem.raw.license_date,
        business_name: selectedItem.name,
      });
    },
    enabled: isOpen && !!selectedItem?.raw.license_date && !!selectedItem?.name,
  });

  const historyData = detailResponse?.data || [];

  return (
    <Modal 
      isOpen={isOpen} 
      onClose={onClose}
      title="인허가 이력 및 상세 정보"
      maxWidth="max-w-5xl"
    >
      {selectedItem && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface p-4 rounded-lg border border-border-standard">
            <div>
              <div className="text-sm text-text-muted mb-1">현재 상호명</div>
              <div className="text-lg font-bold text-text-primary">{selectedItem.name}</div>
            </div>
            <a 
              href={`https://map.naver.com/p/search/${encodeURIComponent(selectedItem.name)}?c=15.00,0,0,0,dh`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors bg-transparent border shadow-sm hover:bg-[#434FF4]/5"
              style={{ color: '#434FF4', borderColor: '#434FF4' }}
            >
              <img src="/naver_map.webp" alt="Naver Map" className="w-4 h-4 object-contain" />
              네이버맵 검색결과
            </a>
          </div>

          <div className="overflow-x-auto border border-border-standard rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>변동 시각</TableHead>
                  <TableHead>상호명</TableHead>
                  <TableHead>대표자명</TableHead>
                  <TableHead>변경 타입</TableHead>
                  <TableHead>업종</TableHead>
                  <TableHead>소재지</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-text-muted">이력 데이터를 불러오는 중입니다...</TableCell>
                  </TableRow>
                ) : isError ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-text-muted">데이터를 불러오는데 실패했습니다.</TableCell>
                  </TableRow>
                ) : historyData.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-text-muted">표시할 이력이 없습니다.</TableCell>
                  </TableRow>
                ) : (
                  historyData.map((item, index) => (
                    <TableRow key={`${item.license_no}-${item.last_event_date}-${index}`}>
                      <TableCell className="font-medium text-brand">
                        {item.last_event_date && item.last_event_date.length === 8 ? formatApprovalDate(item.last_event_date) : '-'}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="text-text-primary font-medium">{item.business_name}</span>
                          {item.prev_business_name && (
                            <span className="text-[11px] text-text-muted mt-0.5 leading-tight">
                              (이전: {item.prev_business_name})
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="text-text-primary">{item.representative_name}</span>
                          {item.prev_representative_name && (
                            <span className="text-[11px] text-text-muted mt-0.5 leading-tight">
                              (이전: {item.prev_representative_name})
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span 
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium border" 
                          style={{ 
                            color: CATEGORY_COLORS[item.infer_update_type || ''] || '#9ca3af', 
                            borderColor: CATEGORY_COLORS[item.infer_update_type || ''] || '#9ca3af',
                            backgroundColor: 'transparent'
                          }}
                        >
                          {CATEGORY_ICONS[item.infer_update_type || ''] && (
                            <span className="flex items-center">
                              {(() => {
                                const Icon = CATEGORY_ICONS[item.infer_update_type || ''];
                                return <Icon weight="bold" size={10} />;
                              })()}
                            </span>
                          )}
                          {item.infer_update_type || '-'}
                        </span>
                      </TableCell>
                      <TableCell className="text-sm text-text-muted">
                        <div className="flex items-center gap-1.5">
                          {INDUSTRY_ICONS[item.industry_type || ''] && (
                            <span className="flex items-center text-text-secondary">
                              {(() => {
                                const Icon = INDUSTRY_ICONS[item.industry_type || ''];
                                return <Icon weight="regular" size={14} />;
                              })()}
                            </span>
                          )}
                          <span>{item.industry_type || '-'}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-text-muted max-w-[200px] truncate" title={item.address}>
                        {item.address}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          
          <div className="pt-4 flex justify-end">
            <Button variant="ghost" onClick={onClose}>닫기</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
