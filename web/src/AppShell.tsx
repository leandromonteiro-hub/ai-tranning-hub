import type { ReactNode } from 'react'

export function AppShell({ user, children }: { user?: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between bg-slate-900 px-4 py-2 text-white">
        <span className="font-bold tracking-tight">ATHLETE HUB</span>
        <nav className="flex gap-6 text-sm">
          <span className="font-semibold">Calendário</span>
          <span className="opacity-60">Dashboard</span>
        </nav>
        <span className="text-sm opacity-80">{user ?? ''}</span>
      </header>
      <main className="p-4">{children}</main>
    </div>
  )
}
