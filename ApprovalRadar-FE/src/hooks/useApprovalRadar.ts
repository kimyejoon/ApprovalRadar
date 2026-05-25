import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, startOfToday } from 'date-fns';
import { fetchApprovals, markApprovalAsRead, type ApprovalData, type ApprovalMappedItem, type ApprovalsResponse } from '@/lib/api';
import { CATEGORY_NAMES, DEFAULT_STATUS_FILTERS, DEFAULT_INDUSTRY_FILTERS, DEFAULT_EXCLUDE_KEYWORDS } from '@/lib/constants';
import { formatPhoneNumber } from '@/lib/utils';

export type SortKey = 'name' | 'owner' | 'approvalDate' | 'phone' | 'id' | 'type';

export function useApprovalRadar() {
  const [selectedItem, setSelectedItem] = useState<ApprovalMappedItem | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(50);
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilters, setStatusFilters] = useState<string[]>(DEFAULT_STATUS_FILTERS);
  const [locationFilters, setLocationFilters] = useState<string[]>([]); // 기본값: 전체 (지역 필터 해제)
  const [industryFilters, setIndustryFilters] = useState<string[]>(DEFAULT_INDUSTRY_FILTERS);
  const [excludeKeywords, setExcludeKeywords] = useState<string[]>(DEFAULT_EXCLUDE_KEYWORDS);
  const [dateRange, setDateRange] = useState<{ from?: Date; to?: Date } | undefined>({
    from: startOfToday(),
    to: startOfToday()
  });

  const { data: apiResponse, isLoading, isError } = useQuery({
    queryKey: ['approvals', currentPage, itemsPerPage, searchQuery, statusFilters, locationFilters, industryFilters, excludeKeywords, dateRange, sortConfig],
    queryFn: () => fetchApprovals({
      page: currentPage,
      size: itemsPerPage,
      search: searchQuery.trim() || undefined,
      start_date: dateRange?.from ? format(dateRange.from, 'yyyyMMdd') : undefined,
      end_date: dateRange?.to ? format(dateRange.to, 'yyyyMMdd') : undefined,
      regions: locationFilters.length > 0 ? locationFilters.join(',') : undefined,
      infer_update_type: statusFilters.length > 0 ? statusFilters.join(',') : undefined,
      industry_type: industryFilters.length > 0 ? industryFilters.join(',') : undefined,
      exclude_keywords: excludeKeywords.length > 0 ? excludeKeywords.join(',') : undefined,
      sort_by: sortConfig ? (
        sortConfig.key === 'id' ? 'license_no' :
        sortConfig.key === 'name' ? 'business_name' :
        sortConfig.key === 'owner' ? 'representative_name' :
        sortConfig.key === 'approvalDate' ? 'last_event_date' :
        sortConfig.key === 'phone' ? 'phone_number' :
        sortConfig.key === 'type' ? 'industry_type' : 'created_at'
      ) : 'created_at',
      sort_order: sortConfig ? sortConfig.direction : 'desc',
    }),
    refetchInterval: 1000 * 60 * 5, // 5 min polling
    refetchOnWindowFocus: true,
    select: (response) => {
      const mappedData: ApprovalMappedItem[] = response.data.map((item: ApprovalData) => {
        const mappedStatus = item.infer_update_type ? CATEGORY_NAMES[item.infer_update_type] || item.infer_update_type : '기타';
        return {
          id: item.license_no,
          name: item.business_name,
          prevName: item.prev_business_name,
          type: item.industry_type || '-',
          location: item.address,
          owner: item.representative_name,
          prevOwner: item.prev_representative_name,
          status: mappedStatus,
          updateDetail: item.infer_update_detail,
          approvalDate: item.last_event_date,
          phone: formatPhoneNumber(item.phone_number),
          isTransfer: false,
          isRead: item.is_read === 1,
          raw: item,
        };
      });
      return {
        ...response,
        data: mappedData,
      };
    }
  });

  const queryClient = useQueryClient();

  const markAsReadMutation = useMutation({
    mutationFn: (license_no: string) => markApprovalAsRead(license_no),
    onMutate: async (license_no) => {
      const queryKey = ['approvals', currentPage, itemsPerPage, searchQuery, statusFilters, locationFilters, industryFilters, excludeKeywords, dateRange, sortConfig];
      await queryClient.cancelQueries({ queryKey });

      // Snapshot the previous value
      const previousData = queryClient.getQueryData<ApprovalsResponse>(queryKey);

      // Optimistically update to the new value
      if (previousData) {
        queryClient.setQueryData<ApprovalsResponse>(queryKey, {
          ...previousData,
          data: previousData.data.map(item => 
            item.license_no === license_no ? { ...item, is_read: 1 } : item
          )
        });
      }

      // Return a context object with the snapshotted value
      return { previousData, queryKey };
    },
    onError: (_err, _newTodo, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(context.queryKey, context.previousData);
      }
    },
    onSettled: (_data, _error, _variables, context) => {
      // Always refetch after error or success to ensure data is correct
      if (context?.queryKey) {
        queryClient.invalidateQueries({ queryKey: context.queryKey });
      }
    },
  });

  const handleMarkAsRead = (license_no: string, currentIsRead: boolean) => {
    if (!currentIsRead) {
      markAsReadMutation.mutate(license_no);
    }
  };

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
  const handleLocationFiltersChange = (locations: string[]) => {
    setLocationFilters(locations);
    setCurrentPage(1);
  };
  const handleDateRangeChange = (range: { from?: Date; to?: Date } | undefined) => {
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
      statusFilters,
      locationFilters,
      industryFilters,
      excludeKeywords,
      dateRange,
    },
    actions: {
      setSelectedItem,
      handleSort,
      handlePageChange,
      handleItemsPerPageChange,
      handleSearch,
      handleStatusFiltersChange: (statuses: string[]) => {
        setStatusFilters(statuses);
        setCurrentPage(1);
      },
      handleLocationFiltersChange,
      handleIndustryFiltersChange: (industries: string[]) => {
        setIndustryFilters(industries);
        setCurrentPage(1);
      },
      handleExcludeKeywordsChange: (keywords: string[]) => {
        setExcludeKeywords(keywords);
        setCurrentPage(1);
      },
      handleDateRangeChange,
      handleMarkAsRead,
    },
    api: {
      data: apiResponse?.data || [],
      meta: apiResponse?.meta,
      isLoading,
      isError,
    }
  };
}
