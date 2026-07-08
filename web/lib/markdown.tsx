import { type ReactNode } from 'react'

/** Parseia negrito inline (**texto**) num ReactNode. */
function inline(text: string, keyBase: string): ReactNode {
  const parts = text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((p) => p !== '')

  if (parts.length === 1) {
    return parts[0]
  }

  return parts.map((p, i) => {
    if (p.length > 4 && p.startsWith('**') && p.endsWith('**')) {
      return <strong key={`${keyBase}-b${i}`}>{p.slice(2, -2)}</strong>
    }
    return <span key={`${keyBase}-t${i}`}>{p}</span>
  })
}

/** Renderiza o subconjunto de markdown que o LLM emite (títulos, negrito,
 *  listas, parágrafos, separador) como JSX estilizado (Tailwind + dark mode).
 *  Qualquer coisa fora do subconjunto degrada para parágrafo simples. */
export function renderMarkdown(text: string | null): ReactNode {
  if (!text || !text.trim()) return null
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let para: string[] = []
  let bullets: string[] = []
  let k = 0

  const flushPara = () => {
    if (para.length) {
      const key = `p${k++}`
      blocks.push(
        <p key={key} className="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          {inline(para.join(' '), key)}
        </p>,
      )
      para = []
    }
  }
  const flushBullets = () => {
    if (bullets.length) {
      const key = `u${k++}`
      blocks.push(
        <ul key={key} className="list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
          {bullets.map((b, i) => <li key={`${key}-${i}`}>{inline(b, `${key}-${i}`)}</li>)}
        </ul>,
      )
      bullets = []
    }
  }

  for (const raw of lines) {
    const line = raw.trim()
    if (line === '') { flushPara(); flushBullets(); continue }
    if (line === '---' || line === '***') {
      flushPara(); flushBullets()
      blocks.push(<hr key={`h${k++}`} className="my-2 border-slate-200 dark:border-slate-700" />)
      continue
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(line)
    if (h) {
      flushPara(); flushBullets()
      const level = h[1].length
      const key = `hd${k++}`
      const cls =
        level === 1
          ? 'mt-3 text-base font-bold text-slate-800 dark:text-slate-100'
          : level === 2
            ? 'mt-3 text-sm font-bold text-slate-800 dark:text-slate-100'
            : 'mt-2 text-sm font-semibold text-slate-700 dark:text-slate-200'
      blocks.push(<div key={key} className={cls}>{inline(h[2], key)}</div>)
      continue
    }
    const b = /^[-*]\s+(.*)$/.exec(line)
    if (b) { flushPara(); bullets.push(b[1]); continue }
    flushBullets()
    para.push(line)
  }
  flushPara(); flushBullets()
  return <div className="space-y-2">{blocks}</div>
}
