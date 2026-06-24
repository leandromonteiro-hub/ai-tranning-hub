"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const base =
  "inline-flex items-center justify-center gap-2 font-semibold transition-colors outline-none focus-visible:ring-2 focus-visible:ring-blue-200 dark:focus-visible:ring-blue-900 disabled:opacity-50 disabled:cursor-not-allowed";

const variants: Record<Variant, string> = {
  primary: "text-white rounded-xl px-5 py-2.5 shadow-sm hover:opacity-95",
  secondary:
    "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-xl px-5 py-2.5 hover:bg-slate-200 dark:hover:bg-slate-700",
  ghost:
    "text-slate-600 dark:text-slate-300 rounded-xl px-4 py-2 hover:bg-slate-100 dark:hover:bg-slate-800",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", className = "", style, ...props }, ref) => {
    // The primary gradient lives in a CSS token, so it goes through inline style.
    const gradient =
      variant === "primary" ? { backgroundImage: "var(--gradient-button)" } : undefined;
    return (
      <button
        ref={ref}
        className={`${base} ${variants[variant]} ${className}`}
        style={{ ...gradient, ...style }}
        {...props}
      />
    );
  },
);

Button.displayName = "Button";
