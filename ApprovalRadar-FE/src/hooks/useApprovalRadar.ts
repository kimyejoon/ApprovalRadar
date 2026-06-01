import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, startOfToday, parse } from 'date-fns';
import { fetchApprovals, markApprovalAsRead, type ApprovalData, type ApprovalMappedItem, type ApprovalsResponse } from '@/lib/api';
import { CATEGORY_NAMES, DEFAULT_STATUS_FILTERS, DEFAULT_INDUSTRY_FILTERS, DEFAULT_EXCLUDE_KEYWORDS } from '@/lib/constants';
import { formatPhoneNumber } from '@/lib/utils';

export type SortKey = 'name' | 'owner' | 'approvalDate' | 'phone' | 'id' | 'type';

function getUrlParams() {
  const hash = window.location.hash || '';
  const questionMarkIndex = hash.indexOf('?');
  if (questionMarkIndex === -1) return new URLSearchParams();
  return new URLSearchParams(hash.substring(questionMarkIndex));
}

function syncStateToUrl(hashPath: string, state: {
  page: number;
  size: number;
  search: string;
  status: string[];
  regions: string[];
  industries: string[];
  exclude: string[];
  from?: Date;
  to?: Date;
  sortKey?: SortKey | null;
  sortDir?: 'asc' | 'desc' | null;
}) {
  const params = new URLSearchParams();
  if (state.page !== 1) params.set('page', state.page.toString());
  if (state.size !== 50) params.set('size', state.size.toString());
  if (state.search) params.set('search', state.search);
  if (state.status.length > 0) params.set('status', state.status.join(','));
  if (state.regions.length > 0) params.set('regions', state.regions.join(','));
  if (state.industries.length > 0) params.set('industries', state.industries.join(','));
  if (state.exclude.length > 0) params.set('exclude', state.exclude.join(','));
  if (state.from) params.set('from', format(state.from, 'yyyyMMdd'));
  if (state.to) params.set('to', format(state.to, 'yyyyMMdd'));
  if (state.sortKey) {
    params.set('sort', state.sortKey);
    params.set('dir', state.sortDir || 'desc');
  }

  const queryStr = params.toString();
  const newHash = `#${hashPath}${queryStr ? '?' + queryStr : ''}`;
  window.history.replaceState(null, '', newHash);
}

export function useApprovalRadar(mode: 'changes' | 'new') {
  const hashPath = mode === 'changes' ? '/change-monitor' : '/new-monitor';

  // ── 1. URL로부터 초기 상태 파싱 ──
  const getInitialState = () => {
    const params = getUrlParams();
    const page = parseInt(params.get('page') || '1', 10);
    const size = parseInt(params.get('size') || '50', 10);
    const search = params.get('search') || '';

    // 모드별 상태(status) 기본값 분기
    let status = DEFAULT_STATUS_FILTERS;
    if (mode === 'new') {
      status = ['신규등록'];
    } else {
      const urlStatus = params.get('status');
      if (urlStatus) {
        status = urlStatus.split(',').filter(Boolean);
      }
    }

    const regions = params.get('regions') ? (params.get('regions') || '').split(',').filter(Boolean) : [];
    const industries = params.get('industries') 
      ? (params.get('industries') || '').split(',').filter(Boolean) 
      : (mode === 'new' ? [] : DEFAULT_INDUSTRY_FILTERS);
    const exclude = params.get('exclude') 
      ? (params.get('exclude') || '').split(',').filter(Boolean) 
      : (mode === 'new' ? [] : DEFAULT_EXCLUDE_KEYWORDS);

    let from = startOfToday();
    let to = startOfToday();
    if (params.get('from')) {
      try {
        from = parse(params.get('from') || '', 'yyyyMMdd', new Date());
      } catch (e) {}
    }
    if (params.get('to')) {
      try {
        to = parse(params.get('to') || '', 'yyyyMMdd', new Date());
      } catch (e) {}
    }

    const sortKey = params.get('sort') as SortKey || null;
    const sortDir = params.get('dir') as 'asc' | 'desc' || 'desc';
    const sortConfig = sortKey ? { key: sortKey, direction: sortDir } : null;

    return { page, size, search, status, regions, industries, exclude, from, to, sortConfig };
  };

  const initial = getInitialState();

  const [selectedItem, setSelectedItem] = useState<ApprovalMappedItem | null>(null);
  const [currentPage, setCurrentPage] = useState(initial.page);
  const [itemsPerPage, setItemsPerPage] = useState(initial.size);
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: 'asc' | 'desc' } | null>(initial.sortConfig);
  const [searchQuery, setSearchQuery] = useState(initial.search);
  const [statusFilters, setStatusFilters] = useState<string[]>(initial.status);
  const [locationFilters, setLocationFilters] = useState<string[]>(initial.regions);
  const [industryFilters, setIndustryFilters] = useState<string[]>(initial.industries);
  const [excludeKeywords, setExcludeKeywords] = useState<string[]>(initial.exclude);
  const [dateRange, setDateRange] = useState<{ from?: Date; to?: Date } | undefined>({
    from: initial.from,
    to: initial.to
  });

  // ── 2. 상태가 변경될 때마다 URL Hash 파라미터 갱신 ──
  useEffect(() => {
    syncStateToUrl(hashPath, {
      page: currentPage,
      size: itemsPerPage,
      search: searchQuery,
      status: statusFilters,
      regions: locationFilters,
      industries: industryFilters,
      exclude: excludeKeywords,
      from: dateRange?.from,
      to: dateRange?.to,
      sortKey: sortConfig?.key,
      sortDir: sortConfig?.direction
    });
  }, [currentPage, itemsPerPage, searchQuery, statusFilters, locationFilters, industryFilters, excludeKeywords, dateRange, sortConfig, hashPath]);

  const { data: apiResponse, isLoading, isError } = useQuery({
    queryKey: ['approvals', currentPage, itemsPerPage, searchQuery, statusFilters, locationFilters, industryFilters, excludeKeywords, dateRange, sortConfig, mode],
    queryFn: () => fetchApprovals({
      page: currentPage,
      size: itemsPerPage,
      search: searchQuery.trim() || undefined,
      start_date: dateRange?.from ? format(dateRange.from, 'yyyyMMdd') : undefined,
      end_date: dateRange?.to ? format(dateRange.to, 'yyyyMMdd') : undefined,
      regions: locationFilters.length > 0 ? locationFilters.join(',') : undefined,
      // mode가 'new'면 무조건 '신규등록'만, 'changes'면 '신규등록'을 필터 목록에서 제외하거나 사용자 선택 필터 적용
      infer_update_type: mode === 'new' 
        ? '신규등록' 
        : (statusFilters.length > 0 ? statusFilters.join(',') : undefined),
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
    onMutate: async (license_no: string) => {
      const queryKey = ['approvals', currentPage, itemsPerPage, searchQuery, statusFilters, locationFilters, industryFilters, excludeKeywords, dateRange, sortConfig, mode];
      await queryClient.cancelQueries({ queryKey });

      const previousData = queryClient.getQueryData<ApprovalsResponse>(queryKey);

      if (previousData) {
        queryClient.setQueryData<ApprovalsResponse>(queryKey, {
          ...previousData,
          data: previousData.data.map(item => 
            item.license_no === license_no ? { ...item, is_read: 1 } : item
          )
        });
      }

      return { previousData, queryKey };
    },
    onError: (_err, _newTodo, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(context.queryKey, context.previousData);
      }
    },
    onSettled: (_data, _error, _variables, context) => {
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
        if (mode === 'changes') {
          setStatusFilters(statuses);
          setCurrentPage(1);
        }
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
