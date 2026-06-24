import { type ReactNode } from "react";

interface CardProps {
  title?: ReactNode;
  /** Optional element rendered on the right side of the header (e.g. a button). */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Show the decorative gradient bar at the top (default: true). */
  bar?: boolean;
}

export function Card({ title, action, children, className = "", bar = true }: CardProps) {
  const hasHeader = title != null || action != null;
  return (
    <div
      className={`bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden ${className}`}
    >
      {bar && <div className="h-1.5" style={{ background: "var(--gradient-bar)" }} />}
      {hasHeader && (
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between gap-4">
          {typeof title === "string" ? (
            <h2 className="font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
          ) : (
            title
          )}
          {action}
        </div>
      )}
      <div className="p-6">{children}</div>
    </div>
  );
}
