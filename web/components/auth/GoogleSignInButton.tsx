"use client";
import { useEffect, useRef } from 'react'

type GsiCredentialResponse = { credential: string }
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: { client_id: string; callback: (r: GsiCredentialResponse) => void }) => void
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void
        }
      }
    }
  }
}

/** Botão oficial do Google (GIS). Sem NEXT_PUBLIC_GOOGLE_CLIENT_ID, não renderiza. */
export function GoogleSignInButton({ onCredential }: { onCredential: (credential: string) => void }) {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
  const host = useRef<HTMLDivElement>(null)
  const cb = useRef(onCredential)
  cb.current = onCredential

  useEffect(() => {
    if (!clientId) return
    const init = () => {
      if (!window.google || !host.current) return
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (r) => cb.current(r.credential),
      })
      window.google.accounts.id.renderButton(host.current, {
        theme: 'outline', size: 'large', width: 320, text: 'continue_with', locale: 'pt-BR',
      })
    }
    if (window.google?.accounts?.id) { init(); return }
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = init
    document.head.appendChild(s)
  }, [clientId])

  if (!clientId) return null
  return <div ref={host} data-testid="google-signin" className="flex justify-center" />
}
