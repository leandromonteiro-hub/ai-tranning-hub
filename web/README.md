# web — Painel admin (Next.js + Tailwind v4)

Scaffold genérico e neutro de um painel administrativo SaaS. Sem identidade de
marca — todos os tokens em `theme/tokens.css` são substituíveis.

## Stack
- Next.js (App Router)
- Tailwind CSS v4 (configuração CSS-first, sem `tailwind.config.js`)
- lucide-react (ícones)
- Dark mode por classe `.dark` no `<html>` (persistido em `localStorage["app-theme"]`)
- Fonte: system UI

## Rodar
```bash
cd web
npm install
npm run dev      # http://localhost:3000
```

## Rotas
- `/login` — tela pública (sem sidebar), grupo `(auth)`
- `/dashboard` — página interna de exemplo (stat cards + tabela vazia), grupo `(app)`
- `/` — redireciona para `/dashboard`

> Os itens de menu `Usuários`, `Relatórios`, `Configurações` e `Permissões` estão
> em `components/Sidebar.tsx` (array `NAV_ITEMS` / `ADMIN_ITEMS`) mas ainda não têm
> páginas — adicione `app/(app)/<rota>/page.tsx` conforme precisar.

## Onde mexer
- **Cores / raios / gradientes:** `theme/tokens.css`
- **Menu lateral:** `components/Sidebar.tsx` (`NAV_ITEMS`, `ADMIN_ITEMS`)
- **Shell autenticado (sidebar + drawer mobile):** `app/(app)/layout.tsx`
- **Componentes reutilizáveis:** `components/ui/{Card,Button,Input,Badge}.tsx`
- **Tema (provider + toggle):** `components/ThemeProvider.tsx`
