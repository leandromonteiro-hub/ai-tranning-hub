import Link from "next/link";
import { HeartPulse, Activity, Flag, Brain } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

const cards = [
  { label: "Anamnese", hint: "status do seu perfil", icon: HeartPulse },
  { label: "Forma (TSB)", hint: "CTL · ATL · TSB", icon: Activity },
  { label: "Próxima prova", hint: "contagem regressiva", icon: Flag },
  { label: "Fase de hoje", hint: "bloco do plano", icon: Brain },
];

export default function OverviewPage() {
  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-800 dark:text-slate-100">
            Visão geral
          </h1>
          <p className="text-sm text-slate-500">Seu painel de treino.</p>
        </div>
        <Link href="/recomendacoes">
          <Button>
            <Brain className="h-4 w-4" />
            Gerar recomendação
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.label}
              className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-5"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400">
                <Icon className="h-5 w-5" />
              </span>
              <p className="mt-4 text-2xl font-bold text-slate-300 dark:text-slate-600">—</p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">{c.label}</p>
              <p className="text-xs text-slate-400">{c.hint}</p>
            </div>
          );
        })}
      </div>

      <Card title="Dados ao vivo">
        <p className="text-sm text-slate-500">
          Os indicadores acima passam a refletir seus dados reais no marco <strong>M2</strong>.
        </p>
      </Card>
    </div>
  );
}
