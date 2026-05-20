import { useQuery } from '@tanstack/react-query';
import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { formatApprovalDate, formatPhoneNumber } from '../../lib/utils';
import { type ApprovalMappedItem, fetchApprovalDetail } from '../../lib/api';
import { CATEGORY_COLORS, CATEGORY_ICONS, INDUSTRY_ICONS } from '@/lib/constants';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table';
import { MemoSection } from './ApprovalDetailModal/MemoSection';

interface ApprovalDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedItem: ApprovalMappedItem | null;
}

export function ApprovalDetailModal({ isOpen, onClose, selectedItem }: ApprovalDetailModalProps) {
  const licenseNo = selectedItem?.raw.license_no;
  const { data: detailResponse, isLoading, isError } = useQuery({
    queryKey: ['approvalDetail', licenseNo],
    queryFn: () => {
      if (!licenseNo) {
        return Promise.reject(new Error('Missing license_no'));
      }
      return fetchApprovalDetail({ license_no: licenseNo });
    },
    enabled: isOpen && !!licenseNo,
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
          {/* 헤더 섹션 */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-surface p-4 rounded-lg border border-border-standard">
            <div>
              <div className="text-sm text-text-muted mb-1">현재 상호명</div>
              <div className="text-lg font-bold text-text-primary">{selectedItem.name}</div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={`https://www.diningcode.com/list.dc?query=${encodeURIComponent(selectedItem.name)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors bg-transparent border shadow-sm hover:bg-[#0CD1E5]/5"
                style={{ color: '#0CD1E5', borderColor: '#0CD1E5' }}
              >
                <img src="/dining_code.jpg" alt="Dining Code" className="w-4 h-4 object-contain rounded-sm" />
                다이닝코드 검색결과
              </a>
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
          </div>

          {/* 메모 섹션 (헤더 ↔ 테이블 사이) */}
          {selectedItem.raw.license_date && selectedItem.name && (
            <MemoSection
              licenseDate={selectedItem.raw.license_date}
              businessName={selectedItem.name}
            />
          )}

          {/* 테이블 섹션 */}
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
                          <span className="text-[11px] text-text-muted mt-0.5 font-mono">{item.license_no}</span>
                          {item.prev_business_name && (
                            <span className="text-[11px] text-brand mt-0.5 leading-tight break-keep">
                              (이전: {item.prev_business_name})
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="text-text-primary">{item.representative_name}</span>
                          {item.phone_number && (
                            <span className="text-[11px] text-text-muted mt-0.5 font-mono">
                              {formatPhoneNumber(item.phone_number)}
                            </span>
                          )}
                          {item.prev_representative_name && (
                            <span className="text-[11px] text-brand mt-0.5 leading-tight break-keep">
                              (이전: {item.prev_representative_name})
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col items-start gap-1">
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
                          {(item.infer_update_detail || item.update_type) && (
                            <span className="text-[11px] text-text-secondary leading-tight break-keep">
                              {item.infer_update_detail || item.update_type}
                            </span>
                          )}
                          {item.business_status && (
                            <span className="text-[11px] text-text-muted leading-tight mt-0.5">
                              {item.business_status}
                              {item.prev_business_status && ` (이전: ${item.prev_business_status})`}
                            </span>
                          )}
                          {item.collected_by && (
                            <span className="text-[10px] text-text-muted/50 mt-1 font-mono">
                              via {({'rolling_scan': 'Rolling Scan', 'chng_dt_poller': 'CHNG_DT Poller', 'tail_ping': 'Tail Ping', 'range_scan': 'Range Scan'} as Record<string, string>)[item.collected_by] || item.collected_by}
                            </span>
                          )}
                        </div>
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
