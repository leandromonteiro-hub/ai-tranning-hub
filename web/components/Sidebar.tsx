"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  BarChart3,
  Settings,
  ShieldCheck,
  LogOut,
  Moon,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { useTheme } from "./ThemeProvider";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

/* Configure the menu here — add/remove items freely. */
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Usuários", href: "/users", icon: Users },
  { label: "Relatórios", href: "/reports", icon: BarChart3 },
  { label: "Configurações", href: "/settings", icon: Settings },
];

/* Optional "Admin" section — omit to hide. */
export const ADMIN_ITEMS: NavItem[] = [
  { label: "Permissões", href: "/admin/roles", icon: ShieldCheck },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();

  const renderItem = (item: NavItem) => {
    const active = pathname === item.href || pathname.startsWith(item.href + "/");
    const Icon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={onNavigate}
        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
          active
            ? "text-white shadow-sm"
            : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
        }`}
        style={active ? { backgroundImage: "var(--gradient-button)" } : undefined}
      >
        <Icon className="h-5 w-5 shrink-0" />
        {item.label}
      </Link>
    );
  };

  return (
    <aside className="flex h-full w-64 flex-col bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 h-16 border-b border-slate-100 dark:border-slate-800">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="" className="h-8 w-8" />
        <span className="font-bold text-slate-800 dark:text-slate-100">Meu App</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {NAV_ITEMS.map(renderItem)}

        {ADMIN_ITEMS.length > 0 && (
          <div className="pt-4 mt-4 border-t border-slate-100 dark:border-slate-800 space-y-1">
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Admin
            </p>
            {ADMIN_ITEMS.map(renderItem)}
          </div>
        )}
      </nav>

      {/* Footer: theme toggle + user + logout */}
      <div className="border-t border-slate-100 dark:border-slate-800 p-3 space-y-1">
        <button
          type="button"
          onClick={toggleTheme}
          className="flex w-full items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
        >
          {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          {theme === "dark" ? "Tema claro" : "Tema escuro"}
        </button>

        <div className="flex items-center gap-3 px-3 py-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-200 dark:bg-slate-700 text-sm font-semibold text-slate-600 dark:text-slate-200">
            MA
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-700 dark:text-slate-200">
              Usuário
            </p>
            <p className="truncate text-xs text-slate-400">user@exemplo.com</p>
          </div>
          <Link
            href="/login"
            aria-label="Sair"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <LogOut className="h-5 w-5" />
          </Link>
        </div>
      </div>
    </aside>
  );
}
