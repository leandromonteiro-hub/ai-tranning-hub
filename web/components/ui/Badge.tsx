import { type ReactNode } from "react";

type BadgeVariant = "success" | "info" | "warning" | "error";

const variants: Record<BadgeVariant, string> = {
  success: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400",
  info: "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400",
  warning: "bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400",
  error: "bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400",
};

export function Badge({
  variant = "info",
  children,
}: {
  variant?: BadgeVariant;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${variants[variant]}`}
    >
      {children}
    </span>
  );
}
