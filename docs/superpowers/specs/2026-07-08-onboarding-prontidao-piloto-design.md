# Prontidão do onboarding para o piloto

**Data:** 2026-07-08 · **Status:** aprovado
**Contexto:** antes de colocar os 10 atletas do piloto, dois furos no onboarding
travariam a experiência: (A) o wizard deixa o atleta avançar com a **anamnese
incompleta** — ele só descobre que falta algo quando a recomendação falha com
422 ("Complete sua anamnese"); (B) o **histórico de treino** (que constrói o
"digital twin" e faz o comparativo Método-tradicional-vs-IA funcionar) **não vem
do Garmin** (o sync só faz backfill de 60 dias e não regenera o twin), e o
onboarding não guia o atleta a importá-lo. Esta spec fecha os dois.

## Decisões (aprovadas pelo usuário)

- **Furo A:** o wizard exige os **9 campos obrigatórios** da anamnese antes de
  avançar (não só "perfil salvo").
- **Furo B:** o histórico entra por **import de arquivos guiado no onboarding**
  (o atleta sobe export do TrainingPeaks/Strava/FIT; a página Importar já
  constrói o twin a partir disso). Garmin permanece só para manter atualizado.
  NÃO estender o backfill do Garmin (risco de rate-limit) — decidido.
- **Zero backend novo:** a página Importar/`imports/upload` já regenera o twin.

## Arquitetura (tudo em `web/`)

### Furo A — validar a anamnese

- `web/lib/anamnese.ts`: novo `isAnamneseComplete(profile: AthleteProfile | null):
  boolean` e `missingRequiredFields(profile): string[]` (rótulos pt-BR dos que
  faltam). Espelha os 9 obrigatórios do backend
  (`profile_context.REQUIRED_FIELDS`): `birth_date, sex, weight_kg, height_cm,
  max_hr, primary_discipline, years_training, goals, weekly_hours`.
- `web/components/onboarding/OnboardingWizard.tsx` (`advanceFromAnamnese`): em vez
  de aceitar qualquer perfil salvo, busca o perfil e só avança se
  `isAnamneseComplete`; senão mostra mensagem clara listando o que falta
  (`missingRequiredFields`). Mantém o tratamento de erro/rede atual.

### Furo B — passo de importar histórico

- **Extração:** o bloco de upload de arquivos hoje embutido em
  `web/components/importar/ImportarView.tsx` (input de arquivo, `POST
  imports/upload`, polling da regeneração do perfil via `jobPoll`, tabela de
  resultado) vira um componente reutilizável
  `web/components/importar/FileUploader.tsx`. `ImportarView` passa a renderizá-lo
  — comportamento idêntico, sem duplicação.
- **Novo passo "Importar histórico"** no `OnboardingWizard`, **entre Anamnese e
  Garmin**: renderiza `<FileUploader />` + texto curto explicando o valor
  ("quanto mais histórico você subir — export do TrainingPeaks/Strava ou
  arquivos FIT —, melhores e mais personalizadas as recomendações; dá para fazer
  depois na página Importar"). **Opcional/pulável** (botão "Pular por enquanto",
  como o Garmin); só a anamnese é obrigatória.
- Fluxo final: **Anamnese (obrigatória) → Importar histórico (opcional) → Garmin
  (opcional) → Concluir.** Atualizar o array `STEPS` e o indicador de progresso.

## Não-objetivos

- Não estender o backfill do Garmin nem regenerar o twin no sync do Garmin
  (decidido: risco de rate-limit; histórico vem por import).
- Não mudar backend (`imports/upload` já dispara `regenerate_profile_task`).
- Não tornar o import obrigatório (o atleta pode não ter export à mão; importa
  depois). Só a anamnese trava.
- Não refazer o `AnamneseView` — a validação vive no gate do wizard (marcar
  campos obrigatórios no form é melhoria futura, fora de escopo).

## Testes (vitest + @testing-library/react)

- `web/lib/__tests__/anamnese.test.ts`: `isAnamneseComplete` true com os 9
  campos; false faltando qualquer um; `missingRequiredFields` lista os corretos.
- `OnboardingWizard`: com perfil incompleto o passo 1 NÃO avança e mostra o que
  falta; com perfil completo avança; o passo "Importar histórico" renderiza o
  `FileUploader` (mockado) e é pulável; concluir segue chamando
  `complete-onboarding`.
- `web/components/importar/__tests__/ImportarView.test.tsx` (ajuste): continua
  passando com o `FileUploader` extraído (o teste que verifica título/upload).
- `FileUploader` (novo teste ou coberto via ImportarView): renderiza o input e o
  botão Enviar desabilitado sem arquivos.
