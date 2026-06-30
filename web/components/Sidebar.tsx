"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  HeartPulse,
  Activity,
  ClipboardCheck,
  Upload,
  Flag,
  CalendarRange,
  Brain,
  Compass,
  ShieldCheck,
  LogOut,
  Moon,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { useTheme } from "./ThemeProvider";
import type { Role } from "@/lib/session";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Início", href: "/", icon: LayoutDashboard },
  { label: "Anamnese", href: "/anamnese", icon: HeartPulse },
  { label: "Forma & Carga", href: "/forma-carga", icon: Activity },
  { label: "Metodologia", href: "/metodologia", icon: Compass },
  { label: "Check-in", href: "/checkin", icon: ClipboardCheck },
  { label: "Importar", href: "/importar", icon: Upload },
  { label: "Provas", href: "/provas", icon: Flag },
  { label: "Plano", href: "/plano", icon: CalendarRange },
  { label: "Recomendações", href: "/recomendacoes", icon: Brain },
];

export const ADMIN_ITEMS: NavItem[] = [
  { label: "Painel do treinador", href: "/admin", icon: ShieldCheck },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "—";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function Sidebar({
  role,
  userName,
  onNavigate,
}: {
  role: Role | null;
  userName: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();

  async function logout() {
    try { await fetch("/api/auth/logout", { method: "POST" }); } catch {}
    window.location.href = "/login";
  }

  const renderItem = (item: NavItem) => {
    const active =
      item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");
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
      <div className="flex items-center gap-3 px-6 h-16 border-b border-slate-100 dark:border-slate-800">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="" className="h-8 w-8" />
        <span className="font-bold text-slate-800 dark:text-slate-100">Meu App</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {NAV_ITEMS.map(renderItem)}

        {role === "ADMIN" && (
          <div className="pt-4 mt-4 border-t border-slate-100 dark:border-slate-800 space-y-1">
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Admin
            </p>
            {ADMIN_ITEMS.map(renderItem)}
          </div>
        )}
      </nav>

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
            {initials(userName)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-700 dark:text-slate-200">
              {userName || "Usuário"}
            </p>
            <p className="truncate text-xs text-slate-400">{role === "ADMIN" ? "Treinador" : "Atleta"}</p>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sair"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <LogOut className="h-5 w-5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
