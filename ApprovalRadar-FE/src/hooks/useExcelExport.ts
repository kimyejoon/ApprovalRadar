import { useState } from 'react';
import { format } from 'date-fns';
import { exportApprovalsExcel } from '@/lib/api';

interface DateRange {
  from?: Date;
  to?: Date;
}

export function useExcelExport(dateRange?: DateRange) {
  const [isExporting, setIsExporting] = useState(false);

  const handleExportExcel = async () => {
    try {
      setIsExporting(true);
      const start_date = dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined;
      const end_date = dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined;
      
      const startStr = dateRange?.from ? format(dateRange.from, 'yyyyMMdd') : undefined;
      const endStr = dateRange?.to ? format(dateRange.to, 'yyyyMMdd') : undefined;
      
      let filename = '대표자변경분.xlsx';
      if (startStr && endStr) {
        if (startStr === endStr) {
          filename = `대표자변경분_${startStr}.xlsx`;
        } else {
          filename = `대표자변경분_${startStr}_${endStr}.xlsx`;
        }
      } else if (startStr) {
        filename = `대표자변경분_${startStr}.xlsx`;
      } else if (endStr) {
        filename = `대표자변경분_${endStr}.xlsx`;
      } else {
        const today = format(new Date(), 'yyyyMMdd');
        filename = `대표자변경분_${today}.xlsx`;
      }
      
      await exportApprovalsExcel({ start_date, end_date }, filename);
    } catch (error) {
      console.error('Excel export failed:', error);
      alert('엑셀 다운로드 중 오류가 발생했습니다.');
    } finally {
      setIsExporting(false);
    }
  };

  return {
    isExporting,
    handleExportExcel,
  };
}
