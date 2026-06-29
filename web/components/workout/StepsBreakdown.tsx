type Step = { label: string; durationS: number; lowW: number | null; highW: number | null; zone: number }

export function StepsBreakdown({ steps }: { steps: Step[] }) {
  return (
    <ul className="space-y-2">
      {steps.map((s, i) => (
        <li key={i} className="text-sm text-slate-700 dark:text-slate-200">
          <span className="font-semibold">{s.label}</span>{' · '}
          <span>{Math.round(s.durationS / 60)} min</span>
          {s.lowW != null && s.highW != null && <span>{' @ '}{s.lowW}–{s.highW} W</span>}
          <span className="text-slate-500 dark:text-slate-400">{' · Zona '}{s.zone}</span>
        </li>
      ))}
    </ul>
  )
}
