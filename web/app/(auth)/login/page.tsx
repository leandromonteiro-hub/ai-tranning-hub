"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError("");
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    setLoading(false);
    if (res.ok) {
      await res.json();
      router.push("/");
      router.refresh();
    } else {
      setError("Falha no login. Verifique email e senha.");
    }
  }

  async function onGoogle(credential: string) {
    setLoading(true);
    setError("");
    const res = await fetch("/api/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
    });
    setLoading(false);
    if (res.ok) {
      await res.json();
      router.push("/");
      router.refresh();
      return;
    }
    const body = await res.json().catch(() => ({ error: "" }));
    if (res.status === 403 && body.error === "invite_required") {
      router.push("/cadastro?google=1");
      return;
    }
    setError("Falha no login com Google. Tente novamente.");
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <div className="w-full max-w-md animate-fade-in">
        <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden">
          <div className="h-1.5" style={{ background: "var(--gradient-bar)" }} />
          <div className="p-8">
            <div className="flex flex-col items-center text-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.svg" alt="" className="h-12 w-12" />
              <h1 className="mt-4 text-2xl font-bold text-slate-800 dark:text-slate-100">Meu App</h1>
              <p className="mt-1 text-sm text-slate-500">Entre para acessar o painel.</p>
            </div>

            <form className="mt-8 space-y-4" onSubmit={onSubmit}>
              <Input
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="voce@exemplo.com"
                autoComplete="username"
              />
              <Input
                label="Senha"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
              />
              {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
              <Button type="submit" className="w-full" disabled={loading}>
                <LogIn className="h-4 w-4" />
                {loading ? "Entrando..." : "Entrar"}
              </Button>
            </form>

            <div className="mt-6 space-y-4">
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" /> ou
                <div className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
              </div>
              <GoogleSignInButton onCredential={onGoogle} />
              <p className="text-center text-sm text-slate-500">
                Novo por aqui? <a href="/cadastro" className="underline">Criar conta</a>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
