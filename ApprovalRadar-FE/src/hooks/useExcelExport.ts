import { useState } from 'react';
import { format } from 'date-fns';
import { exportApprovalsExcel } from '@/lib/api';

interface DateRange {
  from?: Date;
  to?: Date;
}

interface ExcelExportFilters {
  search?: string;
  regions?: string[];
  infer_update_type?: string[];
  industry_type?: string[];
  exclude_keywords?: string[];
}

export function useExcelExport(dateRange?: DateRange, filters?: ExcelExportFilters) {
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

      const search = filters?.search?.trim() || undefined;
      const regions = filters?.regions && filters.regions.length > 0 ? filters.regions.join(',') : undefined;
      const infer_update_type = filters?.infer_update_type && filters.infer_update_type.length > 0 ? filters.infer_update_type.join(',') : undefined;
      const industry_type = filters?.industry_type && filters.industry_type.length > 0 ? filters.industry_type.join(',') : undefined;
      const exclude_keywords = filters?.exclude_keywords && filters.exclude_keywords.length > 0 ? filters.exclude_keywords.join(',') : undefined;
      
      await exportApprovalsExcel({
        start_date,
        end_date,
        search,
        regions,
        infer_update_type,
        industry_type,
        exclude_keywords
      }, filename);
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
