import { useState } from 'react';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { DashboardHeader } from '@/components/ui/DashboardHeader';
import { DashboardIndicators } from '@/components/ui/DashboardIndicators';
import { DashboardFilters } from '@/components/ui/DashboardFilters';
import { ApprovalTable } from '@/components/ui/ApprovalTable';
import { DataTablePagination } from '@/components/ui/DataTablePagination';
import { ApprovalDetailModal } from '@/components/features/ApprovalDetailModal';
import { StatusFilterModal } from '@/components/features/StatusFilterModal';
import { LocationFilterModal } from '@/components/features/LocationFilterModal';
import { IndustryFilterModal } from '@/components/features/IndustryFilterModal';
import { useApprovalRadar } from '@/hooks/useApprovalRadar';

export function DashboardPage() {
  const { state, actions, api } = useApprovalRadar();
  const [isStatusFilterOpen, setIsStatusFilterOpen] = useState(false);
  const [isLocationFilterOpen, setIsLocationFilterOpen] = useState(false);
  const [isIndustryFilterOpen, setIsIndustryFilterOpen] = useState(false);

  const totalPages = api.meta?.total_pages || 1;
  const totalCount = api.meta?.total_count || 0;

  return (
    <DashboardLayout>
      <DashboardHeader totalCount={totalCount} dateRange={state.dateRange} />

      <DashboardIndicators />

      <DashboardFilters 
        searchQuery={state.searchQuery}
        onSearchChange={actions.handleSearch}
        dateRange={state.dateRange}
        onDateRangeChange={actions.handleDateRangeChange}
        statusFilters={state.statusFilters}
        onStatusFiltersChange={actions.handleStatusFiltersChange}
        locationFilters={state.locationFilters}
        onLocationFiltersChange={actions.handleLocationFiltersChange}
        industryFilters={state.industryFilters}
        onIndustryFiltersChange={actions.handleIndustryFiltersChange}
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
        onIndustryClick={() => setIsIndustryFilterOpen(true)}
      />

      <DataTablePagination 
        itemsPerPage={state.itemsPerPage}
        totalCount={totalCount}
        currentPage={state.currentPage}
        totalPages={totalPages}
        onItemsPerPageChange={actions.handleItemsPerPageChange}
        onPageChange={actions.handlePageChange}
      />

      <ApprovalDetailModal 
        isOpen={!!state.selectedItem} 
        onClose={() => actions.setSelectedItem(null)} 
        selectedItem={state.selectedItem} 
      />

      <StatusFilterModal 
        isOpen={isStatusFilterOpen} 
        onClose={() => setIsStatusFilterOpen(false)} 
        statusFilters={state.statusFilters} 
        setStatusFilters={actions.handleStatusFiltersChange} 
        onFilterChange={() => actions.handlePageChange(1)} 
      />

      <LocationFilterModal 
        isOpen={isLocationFilterOpen} 
        onClose={() => setIsLocationFilterOpen(false)} 
        initialLocations={state.locationFilters} 
        onApply={actions.handleLocationFiltersChange} 
      />

      <IndustryFilterModal 
        isOpen={isIndustryFilterOpen} 
        onClose={() => setIsIndustryFilterOpen(false)} 
        industryFilters={state.industryFilters} 
        setIndustryFilters={actions.handleIndustryFiltersChange} 
        onFilterChange={() => actions.handlePageChange(1)} 
      />
    </DashboardLayout>
  );
}
