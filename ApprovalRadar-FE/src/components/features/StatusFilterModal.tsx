import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { CATEGORY_NAMES } from '@/lib/constants';
import { Storefront, UserSwitch, MapPin, IdentificationCard, PlusCircle, Info, Archive, SquaresFour, Tag } from '@phosphor-icons/react';

const STATUS_OPTIONS = [
  { value: '전체', label: '전체', icon: SquaresFour },
  { value: '신규등록', label: CATEGORY_NAMES['신규등록'], icon: PlusCircle },
  { value: '상태변경', label: CATEGORY_NAMES['상태변경'], icon: Info },
  { value: '대표자변경', label: CATEGORY_NAMES['대표자변경'], icon: UserSwitch },
  { value: '변경민원-상호명', label: CATEGORY_NAMES['변경민원-상호명'], icon: Tag },
  { value: '변경민원-주소', label: CATEGORY_NAMES['변경민원-주소'], icon: MapPin },
  { value: '변경민원-성함', label: CATEGORY_NAMES['변경민원-성함'], icon: IdentificationCard },
  { value: '초기수집(과거변경있음)', label: CATEGORY_NAMES['초기수집(과거변경있음)'], icon: Archive },
];

interface StatusFilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  statusFilter: string;
  setStatusFilter: (status: string) => void;
  onFilterChange: () => void;
}

export function StatusFilterModal({ isOpen, onClose, statusFilter, setStatusFilter, onFilterChange }: StatusFilterModalProps) {
  return (
    <Modal 
      isOpen={isOpen} 
      onClose={onClose}
      title="변경 타입 필터"
    >
      <div className="space-y-4">
        <div className="flex flex-col gap-2">
          {STATUS_OPTIONS.map(option => {
            const isSelected = statusFilter === option.value;
            const IconComponent = option.icon;
            return (
              <label 
                key={option.value} 
                className={`flex items-center gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-colors ${
                  isSelected 
                    ? 'border-brand bg-brand/5' 
                    : 'border-border-standard hover:bg-border-subtle/50'
                }`}
              >
                <input 
                  type="radio" 
                  name="status_modal" 
                  value={option.value}
                  checked={isSelected}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    onFilterChange();
                  }}
                  className="accent-brand w-4 h-4"
                />
                <div className="flex items-center gap-2">
                  <IconComponent 
                    weight={isSelected ? 'fill' : 'regular'} 
                    size={18} 
                    className={isSelected ? 'text-brand' : 'text-text-muted'} 
                  />
                  <span className="text-sm font-medium text-text-primary">{option.label}</span>
                </div>
              </label>
            );
          })}
        </div>
        <div className="flex justify-end mt-2">
          <Button variant="secondary" onClick={onClose}>닫기</Button>
        </div>
      </div>
    </Modal>
  );
}
