import {
  Users,
  Activity,
  TrendingUp,
  DollarSign,
  Plus,
  Search,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

const stats = [
  { label: "Usuários ativos", value: "1.248", delta: "+12%", icon: Users },
  { label: "Sessões hoje", value: "342", delta: "+4%", icon: Activity },
  { label: "Conversão", value: "3,8%", delta: "+0,6%", icon: TrendingUp },
  { label: "Receita (mês)", value: "R$ 84,2k", delta: "+8%", icon: DollarSign },
];

const columns = ["Nome", "Email", "Status", "Criado em"];

export default function DashboardPage() {
  return (
    <div className="animate-fade-in space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-800 dark:text-slate-100">
            Dashboard
          </h1>
          <p className="text-sm text-slate-500">Visão geral da sua operação.</p>
        </div>
        <Button>
          <Plus className="h-4 w-4" />
          Novo registro
        </Button>
      </div>

      {/* Stat grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div
              key={s.label}
              className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-5"
            >
              <div className="flex items-center justify-between">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400">
                  <Icon className="h-5 w-5" />
                </span>
                <Badge variant="success">{s.delta}</Badge>
              </div>
              <p className="mt-4 text-2xl font-bold text-slate-800 dark:text-slate-100">
                {s.value}
              </p>
              <p className="text-sm text-slate-500">{s.label}</p>
            </div>
          );
        })}
      </div>

      {/* Main table card */}
      <Card
        title="Registros recentes"
        action={<Button variant="secondary">Exportar</Button>}
      >
        {/* Filters */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input placeholder="Buscar..." className="pl-9" />
          </div>
          <select className="rounded-lg border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-100 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:focus:ring-blue-900/40">
            <option>Todos os status</option>
            <option>Ativo</option>
            <option>Inativo</option>
          </select>
        </div>

        {/* Table */}
        <div className="-mx-6 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                {columns.map((c) => (
                  <th key={c} className="px-6 py-3 font-semibold">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-6 py-16 text-center text-sm text-slate-400"
                >
                  Nenhum registro encontrado.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
