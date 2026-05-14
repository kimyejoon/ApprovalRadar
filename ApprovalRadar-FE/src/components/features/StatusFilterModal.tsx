import { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { CATEGORY_NAMES, CATEGORY_ICONS } from '@/lib/constants';
import { SquaresFour } from '@phosphor-icons/react';

const STATUS_OPTIONS = Object.keys(CATEGORY_NAMES).map(key => ({
  value: key,
  label: CATEGORY_NAMES[key],
  icon: CATEGORY_ICONS[key] || SquaresFour
}));

interface StatusFilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  statusFilters: string[];
  setStatusFilters: (statuses: string[]) => void;
  onFilterChange: () => void;
}

export function StatusFilterModal({ isOpen, onClose, statusFilters, setStatusFilters, onFilterChange }: StatusFilterModalProps) {
  const [localStatuses, setLocalStatuses] = useState<string[]>(statusFilters);

  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocalStatuses(statusFilters); // 모달 열릴 때 외부 상태 동기화 (정당한 패턴)
    }
  }, [isOpen, statusFilters]);

  const handleApply = () => {
    setStatusFilters(localStatuses);
    onFilterChange();
    onClose();
  };

  const toggleStatus = (value: string) => {
    if (localStatuses.includes(value)) {
      setLocalStatuses(localStatuses.filter(s => s !== value));
    } else {
      setLocalStatuses([...localStatuses, value]);
    }
  };

  return (
    <Modal 
      isOpen={isOpen} 
      onClose={onClose}
      title="변경 타입 필터"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          {STATUS_OPTIONS.map(option => {
            const isSelected = localStatuses.includes(option.value);
            const IconComponent = option.icon;
            return (
              <label 
                key={option.value} 
                className={`flex flex-col items-center gap-2 p-3 rounded-lg border cursor-pointer transition-colors ${
                  isSelected 
                    ? 'border-brand bg-brand/5' 
                    : 'border-border-standard hover:bg-border-subtle/50'
                }`}
              >
                <div className="flex w-full justify-between items-center">
                  <IconComponent 
                    weight={isSelected ? 'fill' : 'regular'} 
                    size={20} 
                    className={isSelected ? 'text-brand' : 'text-text-muted'} 
                  />
                  <input 
                    type="checkbox" 
                    value={option.value}
                    checked={isSelected}
                    onChange={() => toggleStatus(option.value)}
                    className="accent-brand w-4 h-4 rounded border-border-standard"
                  />
                </div>
                <span className={`w-full text-left text-sm font-medium ${isSelected ? 'text-brand' : 'text-text-primary'}`}>
                  {option.label}
                </span>
              </label>
            );
          })}
        </div>
        <div className="flex justify-end mt-4 gap-2">
          <Button variant="secondary" onClick={onClose}>취소</Button>
          <Button onClick={handleApply}>적용하기</Button>
        </div>
      </div>
    </Modal>
  );
}
