import React from 'react';

export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-surface border border-border-standard rounded-xl p-5 ${className}`}>
      {children}
    </div>
  );
}
