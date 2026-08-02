import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Política de Privacidade",
};

// Página pública (liberada no middleware): a Whoop exige um link de política
// de privacidade que o atleta vê no fluxo OAuth, antes de ter conta aqui.

const H2 = "mt-8 text-lg font-semibold text-slate-800 dark:text-slate-100";
const P = "mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300";
const LI = "mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-300 list-disc ml-5";

export default function PrivacidadePage() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 px-4 py-10">
      <main className="mx-auto max-w-2xl bg-white dark:bg-slate-900 rounded-2xl shadow border border-slate-100 dark:border-slate-800 p-8">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Política de Privacidade</h1>
        <p className={P}>
          Este serviço gera recomendações de treino de ciclismo personalizadas a partir do seu
          histórico e dos seus dados fisiológicos. Ele está em fase de validação, com acesso por
          convite. Esta página explica quais dados tratamos, para quê, e quais são os seus direitos.
        </p>

        <h2 className={H2}>Dados que coletamos</h2>
        <ul>
          <li className={LI}>
            <strong>Conta:</strong> nome, email e, no login com Google, o identificador da sua conta
            Google. Senhas (quando usadas) são armazenadas apenas como hash.
          </li>
          <li className={LI}>
            <strong>Anamnese:</strong> data de nascimento, sexo, peso, altura, frequência cardíaca
            máxima, disciplina, tempo de treino, objetivos e disponibilidade semanal.
          </li>
          <li className={LI}>
            <strong>Treinos:</strong> atividades importadas por arquivo (CSV, FIT, TCX, GPX) ou
            sincronizadas do Garmin Connect — potência, frequência cardíaca, duração, distância.
          </li>
          <li className={LI}>
            <strong>Recuperação:</strong> HRV, sono, frequência cardíaca de repouso e scores de
            recuperação, vindos do Garmin e/ou da WHOOP, conforme o que você conectar.
          </li>
        </ul>

        <h2 className={H2}>Para que usamos</h2>
        <p className={P}>
          Exclusivamente para gerar suas recomendações de treino e mostrar sua evolução. Parte dos
          dados (métricas de treino e recuperação, nunca suas credenciais) é processada por um
          provedor de IA (Anthropic) para redigir o racional das recomendações. Não vendemos nem
          compartilhamos seus dados com terceiros para publicidade.
        </p>

        <h2 className={H2}>WHOOP e Garmin</h2>
        <p className={P}>
          A conexão com a WHOOP usa o fluxo oficial de autorização (OAuth): você concede acesso de
          leitura a recuperação e sono, e pode revogá-lo a qualquer momento no app da WHOOP ou
          desconectando na página Conexões — o que remove nossos tokens de acesso. Os tokens de
          integração são armazenados criptografados. O mesmo vale para a desconexão do Garmin.
        </p>

        <h2 className={H2}>Armazenamento</h2>
        <p className={P}>
          Os dados ficam em servidor próprio contratado de provedor de nuvem, com acesso restrito,
          backup diário e retenção de backup de 14 dias.
        </p>

        <h2 className={H2}>Seus direitos</h2>
        <p className={P}>
          Nos termos da LGPD, você pode pedir acesso, correção ou exclusão definitiva dos seus dados
          a qualquer momento. Basta escrever para{" "}
          <a href="mailto:leandro.sp@gmail.com" className="underline">
            leandro.sp@gmail.com
          </a>
          . A exclusão remove sua conta, seus treinos e as conexões com Garmin e WHOOP.
        </p>

        <p className="mt-8 text-xs text-slate-400">Última atualização: 2 de agosto de 2026.</p>
      </main>
    </div>
  );
}
