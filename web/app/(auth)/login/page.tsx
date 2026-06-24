import Link from "next/link";
import { LogIn } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <div className="w-full max-w-md animate-fade-in">
        <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden">
          {/* Decorative top bar */}
          <div className="h-1.5" style={{ background: "var(--gradient-bar)" }} />

          <div className="p-8">
            <div className="flex flex-col items-center text-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.svg" alt="" className="h-12 w-12" />
              <h1 className="mt-4 text-2xl font-bold text-slate-800 dark:text-slate-100">
                Meu App
              </h1>
              <p className="mt-1 text-sm text-slate-500">Entre para acessar o painel.</p>
            </div>

            <form className="mt-8 space-y-4">
              <Input label="Email" type="email" placeholder="voce@exemplo.com" />
              <Input label="Senha" type="password" placeholder="••••••••" />
              <Button type="submit" className="w-full">
                <LogIn className="h-4 w-4" />
                Entrar
              </Button>
            </form>

            <div className="my-6 flex items-center gap-3">
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
              <span className="text-xs text-slate-400">ou</span>
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-700" />
            </div>

            <Button variant="secondary" className="w-full">
              Entrar com SSO
            </Button>

            <p className="mt-6 text-center text-xs text-slate-400">
              Ao continuar, você concorda com os termos de uso.
            </p>
          </div>
        </div>

        <p className="mt-4 text-center text-sm text-slate-400">
          <Link
            href="/dashboard"
            className="hover:text-slate-600 dark:hover:text-slate-300"
          >
            Ir para o dashboard →
          </Link>
        </p>
      </div>
    </div>
  );
}
