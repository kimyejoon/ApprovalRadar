import { Button } from '@/components/ui/button';
import { DownloadSimple, CircleNotch } from '@phosphor-icons/react';
import { useIndicatorStore } from '@/store/useIndicatorStore';
import { useExcelExport } from '@/hooks/useExcelExport';

interface DashboardHeaderProps {
  totalCount: number;
  dateRange?: { from?: Date; to?: Date };
  filters?: {
    search?: string;
    regions?: string[];
    infer_update_type?: string[];
    industry_type?: string[];
    exclude_keywords?: string[];
  };
}

export function DashboardHeader({ dateRange, filters }: DashboardHeaderProps) {
  const todayNewCount = useIndicatorStore(s => s.todayNewCount);
  const { isExporting, handleExportExcel } = useExcelExport(dateRange, filters);

  return (
    <div className="flex justify-between items-center mb-6">
      <div>
        <h2 className="text-2xl font-sans font-medium text-text-primary tracking-tight">금일 변동 내역</h2>
        <p className="text-text-muted mt-1 text-sm">
          오늘 발생한 새로운 변동: <span className="text-brand font-medium">{todayNewCount.toLocaleString()}</span>건
        </p>
      </div>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={handleExportExcel} disabled={isExporting} className="gap-2">
          {isExporting ? <CircleNotch weight="bold" className="w-4 h-4 animate-spin" /> : <DownloadSimple weight="bold" className="w-4 h-4" />}
          엑셀 내보내기
        </Button>
      </div>
    </div>
  );
}
