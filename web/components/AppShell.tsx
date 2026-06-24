"use client";

import { useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import type { Role } from "@/lib/session";

export function AppShell({
  role,
  userName,
  children,
}: {
  role: Role | null;
  userName: string;
  children: ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
      <div className="hidden md:block">
        <Sidebar role={role} userName={userName} />
      </div>

      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 md:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Abrir menu"
          className="rounded-lg p-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="" className="h-7 w-7" />
          <span className="font-bold text-slate-800 dark:text-slate-100">Meu App</span>
        </div>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-slate-900/50"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 animate-slide-in-left">
            <div className="relative h-full">
              <Sidebar role={role} userName={userName} onNavigate={() => setMobileOpen(false)} />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Fechar menu"
                className="absolute right-3 top-4 rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="flex-1 overflow-y-auto pt-14 md:pt-0">
        <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
