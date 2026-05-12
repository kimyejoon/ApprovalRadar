import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, startOfToday } from 'date-fns';
import { fetchApprovals, type ApprovalData, type ApprovalMappedItem } from '@/lib/api';

export type SortKey = 'name' | 'owner' | 'approvalDate' | 'phone' | 'id';

export function useApprovalRadar() {
  const [selectedItem, setSelectedItem] = useState<ApprovalMappedItem | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('전체');
  const [locationFilters, setLocationFilters] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | undefined>({
    from: startOfToday(),
    to: startOfToday()
  });

  const { data: apiResponse, isLoading, isError } = useQuery({
    queryKey: ['approvals', currentPage, itemsPerPage, searchQuery, statusFilter, locationFilters, dateRange, sortConfig],
    queryFn: () => fetchApprovals({
      page: currentPage,
      size: itemsPerPage,
      search: searchQuery.trim() || undefined,
      start_date: dateRange?.from ? format(dateRange.from, 'yyyy-MM-dd') : undefined,
      end_date: dateRange?.to ? format(dateRange.to, 'yyyy-MM-dd') : undefined,
      regions: locationFilters.length > 0 ? locationFilters.join(',') : undefined,
      statuses: statusFilter !== '전체' ? statusFilter : undefined,
      sort_by: sortConfig ? (
        sortConfig.key === 'id' ? 'license_no' :
        sortConfig.key === 'name' ? 'business_name' :
        sortConfig.key === 'owner' ? 'representative_name' :
        sortConfig.key === 'approvalDate' ? 'license_date' :
        sortConfig.key === 'phone' ? 'phone_number' : 'created_at'
      ) : 'created_at',
      sort_order: sortConfig ? sortConfig.direction : 'desc',
    }),
    refetchInterval: 1000 * 60 * 5, // 5 min polling
    refetchOnWindowFocus: true,
    select: (response) => {
      const mappedData: ApprovalMappedItem[] = response.data.map((item: ApprovalData) => ({
        id: item.license_no,
        name: item.business_name,
        type: '-', // 업종 필드 부재
        location: item.address,
        owner: item.representative_name,
        status: item.business_status,
        approvalDate: item.license_date,
        phone: item.phone_number,
        isTransfer: false,
        raw: item,
      }));
      return {
        ...response,
        data: mappedData,
      };
    }
  });

  const handleSort = (key: SortKey) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const handlePageChange = (newPage: number) => setCurrentPage(newPage);
  const handleItemsPerPageChange = (newSize: number) => {
    setItemsPerPage(newSize);
    setCurrentPage(1);
  };
  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setCurrentPage(1);
  };
  const handleStatusFilterChange = (status: string) => {
    setStatusFilter(status);
    setCurrentPage(1);
  };
  const handleLocationFiltersChange = (locations: string[]) => {
    setLocationFilters(locations);
    setCurrentPage(1);
  };
  const handleDateRangeChange = (range: { from: Date; to: Date } | undefined) => {
    setDateRange(range);
    setCurrentPage(1);
  };

  return {
    state: {
      selectedItem,
      currentPage,
      itemsPerPage,
      sortConfig,
      searchQuery,
      statusFilter,
      locationFilters,
      dateRange,
    },
    actions: {
      setSelectedItem,
      handleSort,
      handlePageChange,
      handleItemsPerPageChange,
      handleSearch,
      handleStatusFilterChange,
      handleLocationFiltersChange,
      handleDateRangeChange,
    },
    api: {
      data: apiResponse?.data || [],
      meta: apiResponse?.meta,
      isLoading,
      isError,
    }
  };
}
