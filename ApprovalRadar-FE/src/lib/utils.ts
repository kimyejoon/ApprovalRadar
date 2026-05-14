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

export function formatPhoneNumber(phone: string | null | undefined): string {
  if (!phone) return '-';
  
  const clean = phone.replace(/[^0-9]/g, '');
  if (!clean) return phone; // 숫자가 없으면 원본 반환
  
  // 1588-1234 등 (8자리)
  if (clean.length === 8) {
    return clean.replace(/(\d{4})(\d{4})/, '$1-$2');
  } 
  
  // 서울 번호 (02)
  if (clean.startsWith('02')) {
    if (clean.length === 9) {
      return clean.replace(/(\d{2})(\d{3})(\d{4})/, '$1-$2-$3');
    } else if (clean.length === 10) {
      return clean.replace(/(\d{2})(\d{4})(\d{4})/, '$1-$2-$3');
    }
  } else {
    // 그 외 지역 번호 및 휴대폰
    if (clean.length === 10) {
      return clean.replace(/(\d{3})(\d{3})(\d{4})/, '$1-$2-$3');
    } else if (clean.length === 11) {
      return clean.replace(/(\d{3})(\d{4})(\d{4})/, '$1-$2-$3');
    } else if (clean.length === 12) { // 0507 등 안심번호 (12자리)
      return clean.replace(/(\d{4})(\d{4})(\d{4})/, '$1-$2-$3');
    }
  }
  
  return phone; // 형식에 맞지 않으면 원본 반환
}
