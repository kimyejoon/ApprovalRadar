export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-surface border border-border-standard rounded-xl p-5 ${className}`}>
      {children}
    </div>
  );
}

export function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <h2 className="flex items-center gap-2 text-base font-semibold mb-4 text-text-primary">
      {icon}
      {title}
    </h2>
  );
}
