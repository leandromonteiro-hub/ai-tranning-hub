"use client";
import { useIntelligence } from '@/lib/hooks'
import { methodologySummary, type MethodologyTwin } from '@/lib/methodology'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'

const SPLIT_NAMES: Record<string, string> = { z1_pct: 'fácil', z2_pct: 'moderado', z3_pct: 'forte' }
const sign = (n: number) => (n > 0 ? `+${n}` : String(n))

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="text-xl font-bold text-slate-800 dark:text-slate-100">{value}</div>
      {hint && <div className="text-xs text-slate-400">{hint}</div>}
    </div>
  )
}

export function MethodologyView() {
  const { data: intel, isLoading, error } = useIntelligence()

  if (isLoading) return <p className="text-sm text-slate-500">Carregando…</p>
  if (error || !intel) return <p className="text-sm text-red-600">Erro ao carregar a metodologia.</p>

  const twin = intel.twin_seed as MethodologyTwin | null
  const s = methodologySummary(twin)
  const split = twin?.intensity_split
  const tapers = (twin?.tapers ?? []).slice(-6).reverse()
  const terms = (twin?.coach_terms ?? []).slice(0, 15)

  const hasSplit = !!split && (split.z1_pct != null || split.z2_pct != null || split.z3_pct != null)
  const splitPhrase = hasSplit
    ? `${split!.label ?? '—'} — ` +
      (['z1_pct', 'z2_pct', 'z3_pct'] as const)
        .map((k) => `${Math.round((Number(split![k] ?? 0)) * 100)}% ${SPLIT_NAMES[k]}`)
        .join(' · ')
    : null

  const empty = !s.mesoLengthDays && !s.nBlocks && s.taperCount === 0 && !splitPhrase && terms.length === 0

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">🧭 Metodologia &amp; critérios do treinador</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Critérios extraídos do seu histórico real (perfil reverso). É o que a IA usa para personalizar as recomendações.
      </p>

      {empty && (
        <Card><p className="text-sm text-slate-500">Metodologia ainda não computada. Importe mais treinos para gerar o perfil.</p></Card>
      )}

      {(s.mesoLengthDays || s.nBlocks) && (
        <Card title="🧱 Periodização">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Stat label="Mesociclo típico" value={s.mesoLengthDays ? `~${s.mesoLengthDays} dias` : '—'} />
            <Stat label="Blocos detectados" value={s.nBlocks != null ? String(s.nBlocks) : '—'} />
            <Stat
              label="Recuperação"
              value={s.recoveryEveryN ? `a cada ~${s.recoveryEveryN} blocos` : '—'}
              hint={s.recoveryBlocks != null && s.nBlocks != null ? `${s.recoveryBlocks} de ${s.nBlocks} blocos` : undefined}
            />
          </div>
        </Card>
      )}

      {s.taperCount > 0 && (
        <Card title="🎯 Afinação pré-prova (taper)">
          <div className="mb-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <Stat label="TSB no dia da prova (mediana)" value={s.medianTsbRace != null ? sign(Math.round(s.medianTsbRace)) : '—'} />
            <Stat label="Ganho de CTL no taper (mediana)" value={s.medianCtlGain != null ? sign(Math.round(s.medianCtlGain)) : '—'} hint="~22 dias antes" />
            <Stat label="Provas analisadas" value={String(s.taperCount)} />
          </div>
          <div className="space-y-2 border-t border-slate-100 pt-3 dark:border-slate-800">
            {tapers.map((t) => (
              <div key={t.race_date} className="text-xs">
                <span className="font-semibold text-slate-700 dark:text-slate-200">{t.race_date}</span>
                <span className="text-slate-500 dark:text-slate-400">
                  {' · '}CTL {Math.round(t.ctl_race)} · TSB {sign(Math.round(t.tsb_race))} no dia
                </span>
                {t.evidence && <div className="text-slate-400">{t.evidence}</div>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {splitPhrase && (
        <Card title="🎚️ Distribuição de intensidade">
          <p className="text-sm text-slate-700 dark:text-slate-200">{splitPhrase}</p>
          <p className="mt-1 text-xs text-slate-400">A maior parte do volume em baixa intensidade, com proporção decrescente em moderado e forte.</p>
        </Card>
      )}

      {terms.length > 0 && (
        <Card title="🗣️ Termos recorrentes do treinador">
          <div className="flex flex-wrap gap-2">
            {terms.map(([term, count]) => (
              <Badge key={term} variant="info">{term} · {count}</Badge>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-400">Vocabulário mais frequente nas notas dos treinos — informa o tom das recomendações.</p>
        </Card>
      )}
    </div>
  )
}
