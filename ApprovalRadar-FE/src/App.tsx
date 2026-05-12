import { useState } from 'react';
import { DownloadSimple, CaretLeft, CaretRight } from '@phosphor-icons/react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Button } from '@/components/ui/button';
import { DashboardIndicators } from '@/components/ui/DashboardIndicators';
import { DashboardFilters } from '@/components/ui/DashboardFilters';
import { ApprovalTable } from '@/components/ui/ApprovalTable';
import { ApprovalDetailModal } from '@/components/features/ApprovalDetailModal';
import { StatusFilterModal } from '@/components/features/StatusFilterModal';
import { LocationFilterModal } from '@/components/features/LocationFilterModal';
import { useApprovalRadar } from '@/hooks/useApprovalRadar';

export default function App() {
  const { state, actions, api } = useApprovalRadar();
  const [isStatusFilterOpen, setIsStatusFilterOpen] = useState(false);
  const [isLocationFilterOpen, setIsLocationFilterOpen] = useState(false);

  const totalPages = api.meta?.total_pages || 1;
  const totalCount = api.meta?.total_count || 0;
  const startIndex = (state.currentPage - 1) * state.itemsPerPage;

  return (
    <DashboardLayout>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-sans font-medium text-text-primary tracking-tight">금일 변동 내역</h2>
          <p className="text-text-muted mt-1 text-sm">총 {totalCount}건의 인허가 변동 데이터가 실시간으로 수집되고 있습니다.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => console.log('Export Excel')} className="gap-2">
            <DownloadSimple weight="bold" className="w-4 h-4" />
            엑셀 내보내기
          </Button>
        </div>
      </div>

      <DashboardIndicators data={api.data} />

      <DashboardFilters 
        searchQuery={state.searchQuery}
        onSearchChange={actions.handleSearch}
        dateRange={state.dateRange}
        onDateRangeChange={actions.handleDateRangeChange}
        statusFilter={state.statusFilter}
        onStatusReset={() => actions.handleStatusFilterChange('전체')}
        locationFilters={state.locationFilters}
        onLocationRemove={(loc) => actions.handleLocationFiltersChange(state.locationFilters.filter(l => l !== loc))}
      />

      <ApprovalTable 
        data={api.data}
        isLoading={api.isLoading}
        isError={api.isError}
        sortConfig={state.sortConfig}
        onSort={actions.handleSort}
        onRowClick={actions.setSelectedItem}
        onLocationClick={() => setIsLocationFilterOpen(true)}
        onStatusClick={() => setIsStatusFilterOpen(true)}
      />

      <div className="mt-4 flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <span className="text-text-muted">페이지당 행:</span>
          <select 
            className="bg-surface border border-border-standard rounded-md px-2 py-1 text-text-primary focus:outline-none focus:ring-1 focus:ring-brand"
            value={state.itemsPerPage}
            onChange={(e) => actions.handleItemsPerPageChange(Number(e.target.value))}
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>
        </div>
        
        <div className="flex items-center gap-4">
          <span className="text-text-muted">
            총 {totalCount}개 중 {totalCount === 0 ? 0 : startIndex + 1}-{Math.min(startIndex + state.itemsPerPage, totalCount)}
          </span>
          <div className="flex items-center gap-1">
            <Button 
              variant="ghost" 
              size="sm" 
              className="w-8 h-8 p-0 disabled:opacity-30" 
              disabled={state.currentPage === 1}
              onClick={() => actions.handlePageChange(Math.max(1, state.currentPage - 1))}
            >
              <CaretLeft weight="bold" className="w-4 h-4" />
            </Button>
            <Button 
              variant="ghost" 
              size="sm" 
              className="w-8 h-8 p-0 disabled:opacity-30" 
              disabled={state.currentPage === totalPages || totalPages === 0}
              onClick={() => actions.handlePageChange(Math.min(totalPages, state.currentPage + 1))}
            >
              <CaretRight weight="bold" className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>

      <ApprovalDetailModal 
        isOpen={!!state.selectedItem} 
        onClose={() => actions.setSelectedItem(null)} 
        selectedItem={state.selectedItem} 
      />

      <StatusFilterModal 
        isOpen={isStatusFilterOpen} 
        onClose={() => setIsStatusFilterOpen(false)} 
        statusFilter={state.statusFilter} 
        setStatusFilter={actions.handleStatusFilterChange} 
        onFilterChange={() => actions.handlePageChange(1)} 
      />

      <LocationFilterModal 
        isOpen={isLocationFilterOpen} 
        onClose={() => setIsLocationFilterOpen(false)} 
        initialLocations={state.locationFilters} 
        onApply={actions.handleLocationFiltersChange} 
      />
    </DashboardLayout>
  );
}
