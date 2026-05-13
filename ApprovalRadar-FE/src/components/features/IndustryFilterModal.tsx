import { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';
import { INDUSTRY_NAMES, INDUSTRY_ICONS } from '@/lib/constants';
import { ArrowCounterClockwise } from '@phosphor-icons/react';

const INDUSTRY_OPTIONS = Object.keys(INDUSTRY_NAMES).map(key => ({
  value: key,
  label: INDUSTRY_NAMES[key],
  icon: INDUSTRY_ICONS[key]
}));

const MAIN_TARGETS = ['일반음식점', '제과점영업', '휴게음식점'];
const ALL_INDUSTRIES = Object.keys(INDUSTRY_NAMES);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

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
        {/* Quick Select Buttons */}
        <div className="flex flex-wrap justify-center gap-2 w-full max-w-[500px]">
          <Button variant="secondary" onClick={() => setLocalIndustries(MAIN_TARGETS)} className="text-xs py-1 px-3">
            빠른선택: 메인타겟 3종
          </Button>
          <Button variant="secondary" onClick={() => setLocalIndustries(ALL_INDUSTRIES)} className="text-xs py-1 px-3">
            전체 선택
          </Button>
          <Button variant="secondary" onClick={() => setLocalIndustries([])} className="text-xs py-1 px-3 flex items-center gap-1 text-text-muted hover:text-text-primary transition-colors">
            <ArrowCounterClockwise weight="bold" className="w-3.5 h-3.5" />
            초기화
          </Button>
        </div>

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
