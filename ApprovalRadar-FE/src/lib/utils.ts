import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatApprovalDate(dateStr: string) {
  if (!dateStr) return '-';
  
  // YYYYMMDD 형식 처리
  if (/^\d{8}$/.test(dateStr)) {
    const y = dateStr.slice(0, 4);
    const m = parseInt(dateStr.slice(4, 6), 10);
    const d = parseInt(dateStr.slice(6, 8), 10);
    return `${y}년 ${m}월 ${d}일`;
  }

  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;

  const y = date.getFullYear();
  const m = date.getMonth() + 1;
  const d = date.getDate();
  const h = date.getHours();
  const min = date.getMinutes();

  const hasTime = dateStr.includes('T') || /\s\d{2}:/.test(dateStr);
  
  if (hasTime) {
    return `${y}년 ${m}월 ${d}일 ${h}시 ${min}분`;
  }
  return `${y}년 ${m}월 ${d}일`;
}
