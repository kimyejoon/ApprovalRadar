import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { formatApprovalDate } from '../../lib/utils';
import { type ApprovalMappedItem } from '../../lib/api';

interface ApprovalDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedItem: ApprovalMappedItem | null;
}

export function ApprovalDetailModal({ isOpen, onClose, selectedItem }: ApprovalDetailModalProps) {
  return (
    <Modal 
      isOpen={isOpen} 
      onClose={onClose}
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
              <div className="text-text-primary mb-3">{selectedItem.location}</div>
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
                  (selectedItem.status || '').includes('정상') || (selectedItem.status || '').includes('영업') 
                    ? 'bg-brand/10 text-brand' 
                    : 'bg-border-prominent text-text-muted'
                }`}>
                  {selectedItem.status || '-'}
                </span>
              </div>
            </div>
            <div>
              <div className="text-text-muted mb-1">업종</div>
              <div className="text-text-primary">{selectedItem.type}</div>
            </div>
            <div>
              <div className="text-text-muted mb-1">최초 인허가시각</div>
              <div className="text-text-primary">{formatApprovalDate(selectedItem.raw.license_date)}</div>
            </div>
            <div>
              <div className="text-text-muted mb-1">인허가 변동시각</div>
              <div className="text-text-primary text-brand font-medium">{formatApprovalDate(selectedItem.approvalDate)}</div>
            </div>
          </div>
          
          <div className="pt-6 border-t border-border-standard flex justify-end gap-3">
            <Button variant="ghost" onClick={onClose}>닫기</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
