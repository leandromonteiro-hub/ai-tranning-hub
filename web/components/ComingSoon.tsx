import { Card } from "@/components/ui/Card";

export function ComingSoon({ title, milestone }: { title: string; milestone: string }) {
  return (
    <div className="animate-fade-in space-y-6">
      <h1 className="text-xl sm:text-2xl font-bold text-slate-800 dark:text-slate-100">{title}</h1>
      <Card title="Em construção">
        <p className="text-sm text-slate-500">
          Esta tela será portada do Streamlit no marco <strong>{milestone}</strong>. Enquanto isso,
          use o app atual em{" "}
          <a className="text-blue-600 dark:text-blue-400 underline" href="http://localhost:8501">
            localhost:8501
          </a>
          .
        </p>
      </Card>
    </div>
  );
}
