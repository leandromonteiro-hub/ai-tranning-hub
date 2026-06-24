"use client";

import { forwardRef, useId, type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, className = "", id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id ?? generatedId;
    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={`w-full px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-800 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/40 outline-none transition ${className}`}
          {...props}
        />
      </div>
    );
  },
);

Input.displayName = "Input";
