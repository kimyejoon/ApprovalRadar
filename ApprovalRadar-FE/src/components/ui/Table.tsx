import React from 'react';
import { cn } from '../../lib/utils';

export function Table({ className, ...props }: React.HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-auto border border-border-standard rounded-lg bg-background">
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}

export function TableHeader({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("[&_tr]:border-b [&_tr]:border-border-standard", className)} {...props} />;
}

export function TableBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

export function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "border-b border-border-standard transition-colors hover:bg-border-subtle/50 data-[state=selected]:bg-border-subtle",
        className
      )}
      {...props}
    />
  );
}

export function TableHead({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "h-10 px-4 text-left align-middle font-medium text-text-muted has-[[role=checkbox]]:pr-0",
        className
      )}
      {...props}
    />
  );
}

export function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        "p-4 align-middle text-text-secondary has-[[role=checkbox]]:pr-0",
        className
      )}
      {...props}
    />
  );
}

// Custom specialized cell for "code-like" data (IDs, Numbers, Phone)
export function TableCodeCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <TableCell
      className={cn("font-mono text-xs text-text-muted uppercase tracking-wider", className)}
      {...props}
    />
  );
}
