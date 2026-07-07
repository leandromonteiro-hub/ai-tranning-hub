"use client";
import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton'

function signupError(status: number): string {
  if (status === 409) return 'Este email já tem conta — use a página de login.'
  if (status === 403) return 'Código de convite inválido ou já usado.'
  return 'Falha no cadastro. Tente novamente.'
}

export function CadastroForm() {
  const router = useRouter()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [invite, setInvite] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const canSubmit =
    fullName.trim() !== '' && email.trim() !== '' && password.length >= 8 &&
    invite.trim() !== '' && !loading

  async function finish(res: Response) {
    setLoading(false)
    if (res.ok) {
      router.push('/')
      router.refresh()
      return
    }
    setError(signupError(res.status))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setLoading(true); setError('')
    const res = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: fullName, email, password, invite_code: invite.trim().toUpperCase(),
      }),
    })
    await finish(res)
  }

  async function onGoogle(credential: string) {
    if (invite.trim() === '') {
      setError('Preencha o código de convite antes de continuar com o Google.')
      return
    }
    setLoading(true); setError('')
    const res = await fetch('/api/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential, invite_code: invite.trim().toUpperCase() }),
    })
    await finish(res)
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <Input label="Nome completo" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      <Input label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <Input
        label="Senha (mínimo 8 caracteres)"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="new-password"
      />
      <Input
        label="Código de convite"
        value={invite}
        onChange={(e) => setInvite(e.target.value)}
        placeholder="ex.: ABCD2345"
      />
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <Button type="submit" className="w-full" disabled={!canSubmit}>
        <UserPlus className="h-4 w-4" />
        {loading ? 'Criando…' : 'Criar conta'}
      </Button>
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" /> ou
        <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
      </div>
      <GoogleSignInButton onCredential={onGoogle} />
      <p className="text-center text-sm text-slate-500">
        Já tem conta? <a href="/login" className="underline">Entrar</a>
      </p>
    </form>
  )
}
