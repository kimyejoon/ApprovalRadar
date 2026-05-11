import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { KoreaMapSelector } from '../ui/KoreaMapSelector';
import { ArrowCounterClockwise, X } from '@phosphor-icons/react';

const ALL_REGIONS = [
  '서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
  '대전광역시', '울산광역시', '세종특별자치시', '경기도', '강원도',
  '충청북도', '충청남도', '전라북도', '전라남도', '경상북도', '경상남도', '제주특별자치도'
];
const METRO_REGIONS = ['서울특별시', '인천광역시', '경기도', '강원도'];
const NON_METRO_REGIONS = ALL_REGIONS.filter(r => !METRO_REGIONS.includes(r));

interface LocationFilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  tempLocationFilters: string[];
  setTempLocationFilters: (locations: string[] | ((prev: string[]) => string[])) => void;
  onApply: () => void;
}

export function LocationFilterModal({
  isOpen,
  onClose,
  tempLocationFilters,
  setTempLocationFilters,
  onApply,
}: LocationFilterModalProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
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
          <Button variant="secondary" onClick={onClose}>취소</Button>
          <Button variant="default" onClick={onApply}>적용</Button>
        </div>
      </div>
    </Modal>
  );
}
