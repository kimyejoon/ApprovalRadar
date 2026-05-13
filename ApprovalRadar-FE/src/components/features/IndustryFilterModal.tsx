import { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { INDUSTRY_NAMES, INDUSTRY_ICONS } from '@/lib/constants';

const INDUSTRY_OPTIONS = Object.keys(INDUSTRY_NAMES).map(key => ({
  value: key,
  label: INDUSTRY_NAMES[key],
  icon: INDUSTRY_ICONS[key]
}));

interface IndustryFilterModalProps {
  isOpen: boolean;
  onClose: () => void;
  industryFilters: string[];
  setIndustryFilters: (industries: string[]) => void;
  onFilterChange: () => void;
}

export function IndustryFilterModal({ isOpen, onClose, industryFilters, setIndustryFilters, onFilterChange }: IndustryFilterModalProps) {
  const [localIndustries, setLocalIndustries] = useState<string[]>(industryFilters);

  useEffect(() => {
    if (isOpen) {
      setLocalIndustries(industryFilters);
    }
  }, [isOpen, industryFilters]);

  const handleApply = () => {
    setIndustryFilters(localIndustries);
    onFilterChange();
    onClose();
  };

  const toggleIndustry = (value: string) => {
    if (localIndustries.includes(value)) {
      setLocalIndustries(localIndustries.filter(i => i !== value));
    } else {
      setLocalIndustries([...localIndustries, value]);
    }
  };

  return (
    <Modal 
      isOpen={isOpen} 
      onClose={onClose}
      title="업종 필터"
    >
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          {INDUSTRY_OPTIONS.map(option => {
            const isSelected = localIndustries.includes(option.value);
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
                    onChange={() => toggleIndustry(option.value)}
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
