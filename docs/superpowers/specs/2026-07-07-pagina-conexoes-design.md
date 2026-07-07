# Página "Conexões" (casa dedicada p/ conectar dispositivos)

**Data:** 2026-07-07 · **Status:** aprovado
**Contexto:** o `GarminCard` vive escondido dentro da página Importar (e no
wizard de onboarding). Com o piloto em produção e o Wahoo no horizonte, o
atleta precisa de um lugar óbvio para conectar dispositivos. Esta spec cria
uma página **Conexões** dedicada e move o card do Garmin para lá.

## Decisões (aprovadas pelo usuário)

- **Página Conexões agora**; Wahoo em spec própria quando as credenciais de
  parceiro chegarem (partner-gated: `partnerships@wahoofitness.com`). Sem card
  "em breve" — nada de Wahoo nesta entrega.
- **Zero backend novo**: a rota/endpoints do Garmin já existem; só muda a UI.
- O `GarminCard` **não é modificado** — só reposicionado.

## Arquitetura

- `web/app/(app)/conexoes/page.tsx` (server, fino) → `<ConexoesView />` (client),
  padrão de `anamnese/page.tsx`.
- `web/components/conexoes/ConexoesView.tsx` — título "Conexões" + subtítulo,
  e uma grade de cards de provedor que hoje contém só `<GarminCard />`. A grade
  é o ponto de extensão: um futuro `WahooCard` entra como mais um filho, sem
  refatorar.
- **Sidebar** (`web/components/Sidebar.tsx`): novo item em `NAV_ITEMS`
  `{ label: "Conexões", href: "/conexoes", icon: Plug }` (lucide-react `Plug`),
  posicionado logo após "Importar".
- **ImportarView** (`web/components/importar/ImportarView.tsx`): remove
  `<GarminCard />` e o import dele; adiciona uma linha curta com link:
  "Conecte um dispositivo em Conexões para importar automaticamente"
  (`<Link href="/conexoes">`). Importar volta a ser só o upload manual.
- **OnboardingWizard** (`web/components/onboarding/OnboardingWizard.tsx`):
  inalterado — o passo 2 segue renderizando `<GarminCard />` diretamente.

## Estados e erros

Herdados do `GarminCard` (já tratados lá: 503→não renderiza, loading, connect/
MFA, connected, needs_reauth). A `ConexoesView` não adiciona lógica de dados;
é layout + composição.

## Testes (vitest + @testing-library/react)

- `web/components/conexoes/__tests__/ConexoesView.test.tsx`: renderiza o título
  "Conexões" e contém o `GarminCard` (mockado por `data-testid="garmin-card"`,
  mesmo padrão dos testes existentes).
- `web/components/importar/__tests__/ImportarView.test.tsx` (ajuste): o
  `GarminCard` **não** é mais renderizado; existe um link para `/conexoes`.
- `web/components/__tests__/Sidebar.test.tsx` (novo OU ajuste, se existir):
  o nav contém "Conexões" apontando para `/conexoes`. Se não houver teste de
  Sidebar, criar um mínimo que renderiza `NAV_ITEMS` e checa o item.

## Fora de escopo

- Integração Wahoo (spec própria; bloqueada em credencial de parceiro).
- Qualquer mudança no `GarminCard` ou no backend do Garmin.
- Página de "Integrações" genérica com abas/config além dos cards de provedor.
