import { Button } from '../ui/button';
import { Modal } from '../ui/Modal';

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
      title="영업상태 필터"
    >
      <div className="space-y-4">
        <div className="flex flex-col gap-2">
          {['전체', '영업/정상', '폐업'].map(status => (
            <label 
              key={status} 
              className={`flex items-center gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-colors ${
                statusFilter === status 
                  ? 'border-brand bg-brand/5' 
                  : 'border-border-standard hover:bg-border-subtle/50'
              }`}
            >
              <input 
                type="radio" 
                name="status_modal" 
                value={status}
                checked={statusFilter === status}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  onFilterChange();
                }}
                className="accent-brand w-4 h-4"
              />
              <span className="text-sm font-medium text-text-primary">{status}</span>
            </label>
          ))}
        </div>
        <div className="flex justify-end mt-2">
          <Button variant="secondary" onClick={onClose}>닫기</Button>
        </div>
      </div>
    </Modal>
  );
}
