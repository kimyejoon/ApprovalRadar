import { UserSwitch, MapPin, PlusCircle, Info, Archive, Tag, Coffee, ForkKnife, Cake, Martini, Wine, CookingPot, type Icon } from '@phosphor-icons/react';

export const CATEGORY_NAMES: Record<string, string> = {
  '신규등록': '신규등록',
  '상태변경': '상태 변경',
  '대표자변경': '대표 변경',
  '변경민원-상호명': '상호 변경',
  '변경민원-주소': '주소 변경',
  '초기수집(과거변경있음)': '기타',
};

export const CHANGE_CATEGORIES = ['대표자변경', '상태변경', '변경민원-상호명', '변경민원-주소', '초기수집(과거변경있음)'];
export const NEW_CATEGORIES = ['신규등록'];

export const CATEGORY_COLORS: Record<string, string> = {
  '신규등록': '#434FF4',
  '상태변경': '#ef4444',
  '대표자변경': '#f59e0b',
  '변경민원-상호명': '#8b5cf6',
  '변경민원-주소': '#06b6d4',
  '초기수집(과거변경있음)': '#9ca3af',
};

export const CATEGORY_ICONS: Record<string, Icon> = {
  '신규등록': PlusCircle,
  '상태변경': Info,
  '대표자변경': UserSwitch,
  '변경민원-상호명': Tag,
  '변경민원-주소': MapPin,
  '초기수집(과거변경있음)': Archive,
};

export const INDUSTRY_NAMES: Record<string, string> = {
  '휴게음식점': '휴게음식점',
  '일반음식점': '일반음식점',
  '제과점영업': '제과점영업',
  '유흥주점영업': '유흥주점영업',
  '단란주점': '단란주점',
  '위탁급식영업': '위탁급식영업',
};

export const INDUSTRY_COLORS: Record<string, string> = {
  '휴게음식점': '#f59e0b',
  '일반음식점': '#3b82f6',
  '제과점영업': '#ec4899',
  '유흥주점영업': '#8b5cf6',
  '단란주점': '#a855f7',
  '위탁급식영업': '#10b981',
};

export const INDUSTRY_ICONS: Record<string, Icon> = {
  '휴게음식점': Coffee,
  '일반음식점': ForkKnife,
  '제과점영업': Cake,
  '유흥주점영업': Martini,
  '단란주점': Wine,
  '위탁급식영업': CookingPot,
};

// ─── 대시보드 기본 필터 초기값 ─────────────────────────────────────────────────
// 변경이 필요한 경우 이 파일만 수정하면 useApprovalRadar.ts에 자동 반영됩니다.

/** 상태 유형 기본 필터 */
export const DEFAULT_STATUS_FILTERS: string[] = ['대표자변경'];

/** 업종 기본 필터 */
export const DEFAULT_INDUSTRY_FILTERS: string[] = ['일반음식점', '제과점영업', '휴게음식점'];

/** 상호명 제외 기본 키워드 */
export const DEFAULT_EXCLUDE_KEYWORDS: string[] = ['세븐일레븐', '코리아세븐'];

