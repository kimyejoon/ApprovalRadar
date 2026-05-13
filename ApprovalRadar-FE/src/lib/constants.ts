import { Storefront, UserSwitch, MapPin, IdentificationCard, PlusCircle, Info, Archive, Tag, type Icon } from '@phosphor-icons/react';

export const CATEGORY_NAMES: Record<string, string> = {
  '신규등록': '신규등록',
  '상태변경': '상태 변경',
  '대표자변경': '대표 변경',
  '변경민원-상호명': '상호 변경',
  '변경민원-주소': '주소 변경',
  '변경민원-성함': '성함 변경',
  '초기수집(과거변경있음)': '기타',
};

export const CATEGORY_COLORS: Record<string, string> = {
  '신규등록': '#434FF4',
  '상태변경': '#ef4444',
  '대표자변경': '#f59e0b',
  '변경민원-상호명': '#8b5cf6',
  '변경민원-주소': '#06b6d4',
  '변경민원-성함': '#10b981',
  '초기수집(과거변경있음)': '#9ca3af',
};

export const CATEGORY_ICONS: Record<string, Icon> = {
  '신규등록': PlusCircle,
  '상태변경': Info,
  '대표자변경': UserSwitch,
  '변경민원-상호명': Tag,
  '변경민원-주소': MapPin,
  '변경민원-성함': IdentificationCard,
  '초기수집(과거변경있음)': Archive,
};
