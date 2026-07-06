# Garmin Connect UI — card de conexão na página Importar (web/)

**Data:** 2026-07-06 · **Status:** aprovado
**Contexto:** o backend do sync Garmin (PR #5, merged) está completo e validado
ponta a ponta com a conta real do piloto, mas o onboarding foi feito via curl.
Esta spec cobre a UI que permite ao atleta conectar/gerenciar a própria conta.

## Decisões (aprovadas pelo usuário)

- **Frontend:** somente `web/` (Next.js). O Streamlit é legado e está sendo
  desativado; não recebe esta UI.
- **Localização:** card "Garmin Connect" na página **Importar**
  (`web/app/(app)/importar/`), acima do card de upload manual. Sem item novo
  no menu; a página já é "onde os dados entram".
- **Fluxo:** card único com **estados inline** (sem modal/drawer/wizard) —
  o conteúdo do card muda conforme o status da conexão.

## Arquivos

| Arquivo | Papel |
|---|---|
| `web/components/importar/GarminCard.tsx` | novo — client component com a máquina de estados |
| `web/components/importar/__tests__/GarminCard.test.tsx` | novo — testes vitest |
| `web/lib/hooks.ts` | + `useGarminStatus()` (SWR em `garmin/status`) |
| `web/lib/types.ts` | + `GarminStatus`, `GarminConnectResponse`, `GarminSyncResponse` |
| `web/app/(app)/importar/...` | renderiza `<GarminCard />` acima do upload |
| `backend/app/api/routes/garmin.py` | 401→**400** em connect/connect-mfa (ver §Backend) |
| `backend/app/tests/test_garmin/test_api.py` | asserts 401→400 |

Reuso obrigatório: `Card`/`Button`/`Input`/`Badge` (`web/components/ui/`),
`pollDecision` (`web/lib/jobPoll.ts`), `apiFetch`/`jsonFetcher` (`web/lib/api.ts`).
UI inteira em pt-BR, seguindo o padrão visual das outras views.

## Estados do card

Dirigidos por `GET /garmin/status` (`{status, last_sync_at, needs_reauth,
last_error}`) mais estado local do fluxo:

1. **Carregando** — skeleton discreto (sem spinner grande).
2. **Feature desligada** — `GET garmin/status` retorna **503** quando
   `garmin_token_key` não está configurado → o card **não renderiza nada**.
3. **DISCONNECTED** — texto de 1–2 linhas: importa atividades e wellness
   diariamente e envia treinos aceitos ao calendário Garmin. **Checkbox de
   consentimento** (obrigatório, desmarcado por padrão): "Autorizo o uso das
   minhas credenciais para sincronizar com o Garmin Connect (integração
   não-oficial)". Form email + senha; botão "Conectar" só habilita com
   consentimento marcado e campos preenchidos. Submit → `POST garmin/connect`.
   - `needs_mfa: false` → revalida status (vai a CONNECTED).
   - `needs_mfa: true` → estado AWAITING_MFA.
   - A senha vive apenas no state do form; nunca é logada nem persistida no
     cliente.
4. **AWAITING_MFA** — input de código (6 dígitos, autofocus) + aviso "o código
   vale ~5 minutos" + link "Recomeçar" (volta ao form de credenciais). Submit →
   `POST garmin/connect/mfa` com `{code}`.
5. **CONNECTED** — Badge verde "Conectado", linha "Última sincronização:
   <relativo, ex. 'há 2 h' | 'nunca'>", botões:
   - **Sincronizar agora** → `POST garmin/sync` → `{task_id}` → polling
     `GET jobs/{task_id}` a cada ~2 s com `pollDecision` (máx. ~120 tentativas
     ≈ 4 min — o primeiro sync do piloto levou 3min18s). Botão desabilitado + "Sincronizando…"
     durante; ao terminar, revalida o SWR de status e mostra "Sincronizado ✓"
     ou mensagem de erro. `task_id: null` (broker fora) → erro amigável.
   - **Desconectar** → confirmação inline (trocar o botão por "Confirmar
     desconexão? [Sim] [Cancelar]") → `DELETE garmin/disconnect` → revalida.
6. **NEEDS_REAUTH** — Badge âmbar "Reconexão necessária" + `last_error` (se
   houver) + o mesmo form de credenciais do estado 3 (com consentimento já
   implícito na reconexão — sem checkbox de novo).

## Backend: 401 → 400 em falha de credencial Garmin

`apiFetch` (web/lib/api.ts) trata **qualquer 401 como sessão expirada** e
desloga o usuário do app. Hoje `POST /garmin/connect` e `/connect/mfa`
retornam 401 para credencial/código Garmin inválido — isso deslogaria o
atleta ao errar a senha da Garmin. Mudança: esses dois endpoints passam a
retornar **400** com o mesmo `detail`. O 401 fica reservado à sessão do app.
Nenhuma outra rota muda. Ajustar asserts em `test_api.py`.

## Erros (todos inline no card, nenhum derruba a página)

| Caso | Tratamento |
|---|---|
| 400 no connect | "Email ou senha da Garmin inválidos." |
| 400 no MFA | "Código incorreto ou expirado." |
| 409 no MFA (TTL 5 min estourado) | volta ao form de credenciais com aviso "Tempo esgotado — conecte de novo." |
| 429 (rate limit Garmin) | "Muitas tentativas — aguarde alguns minutos." |
| rede / 5xx | "Erro ao conectar. Tente novamente." |
| polling do sync dá FAILURE/giveup | "A sincronização falhou/está demorando — os dados chegam no sync diário automático." |

## Testes (`GarminCard.test.tsx`, vitest + @testing-library/react)

- Render de cada estado a partir do status mockado (disconnected, awaiting
  MFA, connected com/sem `last_sync_at`, needs_reauth, 503 → nada).
- Consentimento desmarcado mantém "Conectar" desabilitado.
- Fluxo connect → `needs_mfa:true` → tela MFA → sucesso → revalida.
- 400 mostra mensagem inline e **não** redireciona para /login.
- Sincronizar agora: polling até SUCCESS revalida status; FAILURE mostra erro.
- Desconectar exige confirmação inline antes do DELETE.

Backend: nos testes existentes de `test_api.py`, trocar os asserts de 401
para 400 nos casos de credencial/MFA inválidos (auth de sessão intocada).

## Fora de escopo

- UI no Streamlit (legado).
- Página de integrações genérica; outras integrações (TrainingPeaks,
  athletedata) ganham casa quando existirem.
- Exibir progresso granular do sync (contagem de atividades) — o endpoint de
  job não expõe isso hoje.
