import { CadastroForm } from "@/components/auth/CadastroForm";

export default function CadastroPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <div className="w-full max-w-md animate-fade-in">
        <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-100 dark:border-slate-800 overflow-hidden">
          <div className="h-1.5" style={{ background: "var(--gradient-bar)" }} />
          <div className="p-8">
            <div className="flex flex-col items-center text-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.svg" alt="" className="h-12 w-12" />
              <h1 className="mt-4 text-2xl font-bold text-slate-800 dark:text-slate-100">Criar conta</h1>
              <p className="mt-1 text-sm text-slate-500">
                O piloto é por convite — você recebeu um código do treinador.
              </p>
            </div>
            <div className="mt-8">
              <CadastroForm />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
