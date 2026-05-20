import React from 'react';

export function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
      {icon}
      {title}
    </h2>
  );
}
