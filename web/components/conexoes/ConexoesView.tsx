"use client";
import { GarminCard } from '@/components/importar/GarminCard'

export function ConexoesView() {
  return (
    <div className="animate-fade-in space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100 sm:text-2xl">Conexões</h1>
        <p className="text-sm text-slate-500">
          Conecte seus dispositivos para importar treinos e recuperação automaticamente.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <GarminCard />
      </div>
    </div>
  )
}
