# Next.js Port — M1 Fundação (auth BFF + shell) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao painel `web/` autenticação real contra o FastAPI via BFF (cookie httpOnly), proteção de rotas, helper de dados (SWR) e um shell navegável com role-gating — sem tocar no Streamlit.

**Architecture:** O navegador só fala com o Next. Route Handlers (`/api/auth/*`, `/api/proxy/[...path]`) repassam ao FastAPI anexando o JWT lido de um cookie httpOnly. `middleware.ts` exige o cookie nas rotas autenticadas. O layout `(app)` é um Server Component que lê a sessão e renderiza um shell cliente (`AppShell`) com a sidebar real e role-gating.

**Tech Stack:** Next.js 15 (App Router), TypeScript, Tailwind v4, SWR, Vitest + Testing Library, lucide-react.

## Global Constraints

- **BFF obrigatório:** o navegador NUNCA chama o FastAPI direto — sempre via `/api/...` do Next.
- **Cookie:** `aath_token`, `httpOnly`, `sameSite: "lax"`, `secure` só em produção, `path: "/"`, `maxAge` 1 dia.
- **API base server-side:** env `API_BASE_URL`, default `http://localhost:8000/api/v1` (sem barra final).
- **Rotas em pt-BR.** Placeholders neutros mantidos ("Meu App") onde não há conteúdo real.
- **Comandos rodam dentro de `web/`:** testes `npm test` (= `vitest run`); build `npm run build`.
- **Streamlit (`frontend/`) intocado.**
- **Pré-requisitos para verificação ao vivo:** stack de fundo no ar (`docker compose up -d` → API em `:8000`) e `seed` aplicado (atleta `athlete1@athletehub.example.com`/`athlete1_pwd`, admin `admin@athletehub.example.com`/`admin_dev_pwd`). Dev server: `npm run dev` (`:3000`).
- Commits frequentes, um por task.

---

### Task 1: Helpers puros (`config`, `session`) + ferramentas de teste

**Files:**
- Modify: `web/package.json` (add dep `swr`; devDeps de teste; script `test`)
- Create: `web/vitest.config.ts`
- Create: `web/vitest.setup.ts`
- Create: `web/lib/config.ts`
- Create: `web/lib/session.ts`
- Test: `web/lib/__tests__/config.test.ts`, `web/lib/__tests__/session.test.ts`

**Interfaces:**
- Produces: `resolveApiUrl(path: string, search?: string): string`; `decodeJwtRole(token: string): Role | null`; `getSession(): Promise<{token: string; role: Role|null} | null>`; `TOKEN_COOKIE = "aath_token"`; `type Role = "ATHLETE" | "ADMIN"`.

- [ ] **Step 1: Adicionar dependências e script de teste** — em `web/package.json`, acrescentar `"swr": "^2.3.0"` em `dependencies`; em `devDependencies` adicionar `"vitest": "^3.0.5"`, `"@vitejs/plugin-react": "^4.3.4"`, `"jsdom": "^26.0.0"`, `"@testing-library/react": "^16.2.0"`, `"@testing-library/jest-dom": "^6.6.3"`; em `scripts` adicionar `"test": "vitest run"`.

- [ ] **Step 2: Instalar**

Run: `cd web && npm install`
Expected: instala sem erros.

- [ ] **Step 3: Criar a config do Vitest** — `web/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
});
```

`web/vitest.setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Escrever os testes que falham** — `web/lib/__tests__/config.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { resolveApiUrl } from "../config";

describe("resolveApiUrl", () => {
  it("junta base e path", () => {
    expect(resolveApiUrl("athletes/me")).toMatch(/\/api\/v1\/athletes\/me$/);
  });
  it("tira barras iniciais do path", () => {
    expect(resolveApiUrl("/races")).toMatch(/\/api\/v1\/races$/);
  });
  it("anexa query string", () => {
    expect(resolveApiUrl("recommendations/sample.zwo", "template=vo2max&ftp=250")).toMatch(
      /sample\.zwo\?template=vo2max&ftp=250$/,
    );
  });
});
```

`web/lib/__tests__/session.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { decodeJwtRole } from "../session";

function makeToken(payload: object): string {
  const b64 = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `header.${b64}.sig`;
}

describe("decodeJwtRole", () => {
  it("lê ADMIN", () => expect(decodeJwtRole(makeToken({ role: "ADMIN" }))).toBe("ADMIN"));
  it("lê ATHLETE", () => expect(decodeJwtRole(makeToken({ role: "ATHLETE" }))).toBe("ATHLETE"));
  it("null para role desconhecido", () =>
    expect(decodeJwtRole(makeToken({ role: "X" }))).toBeNull());
  it("null para token inválido", () => expect(decodeJwtRole("nao-e-jwt")).toBeNull());
});
```

- [ ] **Step 5: Rodar para ver falhar**

Run: `cd web && npm test`
Expected: FAIL (módulos `../config` e `../session` não existem).

- [ ] **Step 6: Implementar `lib/config.ts`**

```ts
const RAW_BASE = process.env.API_BASE_URL ?? "http://localhost:8000/api/v1";

/** API base sem barra final. */
export const API_BASE_URL = RAW_BASE.replace(/\/+$/, "");

/** Junta a base da API com um path (sem barra inicial) + query string opcional. */
export function resolveApiUrl(path: string, search = ""): string {
  const clean = path.replace(/^\/+/, "");
  const qs = search && !search.startsWith("?") ? `?${search}` : search;
  return `${API_BASE_URL}/${clean}${qs}`;
}
```

- [ ] **Step 7: Implementar `lib/session.ts`**

```ts
import { cookies } from "next/headers";

export type Role = "ATHLETE" | "ADMIN";
export const TOKEN_COOKIE = "aath_token";

/** Decodifica o payload do JWT (SEM verificar assinatura — só para gatear UI). */
export function decodeJwtRole(token: string): Role | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = Buffer.from(payload, "base64url").toString("utf-8");
    const role = JSON.parse(json).role;
    return role === "ADMIN" || role === "ATHLETE" ? role : null;
  } catch {
    return null;
  }
}

/** Server-only: lê o cookie de auth e decodifica o papel. */
export async function getSession(): Promise<{ token: string; role: Role | null } | null> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  return { token, role: decodeJwtRole(token) };
}
```

- [ ] **Step 8: Rodar os testes (verde)**

Run: `cd web && npm test`
Expected: PASS (7 testes).

- [ ] **Step 9: Commit**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts web/vitest.setup.ts web/lib/config.ts web/lib/session.ts web/lib/__tests__/
git commit -m "feat(web): API url + JWT session helpers with vitest"
```

---

### Task 2: Route Handlers de login/logout

**Files:**
- Create: `web/app/api/auth/login/route.ts`
- Create: `web/app/api/auth/logout/route.ts`

**Interfaces:**
- Consumes: `resolveApiUrl`, `decodeJwtRole`, `TOKEN_COOKIE`.
- Produces: `POST /api/auth/login` `{email,password}` → grava cookie, responde `{ok:true, role}`; `POST /api/auth/logout` → apaga cookie.

- [ ] **Step 1: Implementar o login** — `web/app/api/auth/login/route.ts`:

```ts
import { NextResponse } from "next/server";
import { resolveApiUrl } from "@/lib/config";
import { decodeJwtRole, TOKEN_COOKIE } from "@/lib/session";

export async function POST(request: Request) {
  const { email, password } = await request.json();
  const body = new URLSearchParams({ username: email ?? "", password: password ?? "" });

  const res = await fetch(resolveApiUrl("auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    return NextResponse.json({ error: "Credenciais inválidas" }, { status: res.status });
  }

  const { access_token } = await res.json();
  const response = NextResponse.json({ ok: true, role: decodeJwtRole(access_token) });
  response.cookies.set(TOKEN_COOKIE, access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24,
  });
  return response;
}
```

- [ ] **Step 2: Implementar o logout** — `web/app/api/auth/logout/route.ts`:

```ts
import { NextResponse } from "next/server";
import { TOKEN_COOKIE } from "@/lib/session";

export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(TOKEN_COOKIE);
  return response;
}
```

- [ ] **Step 3: Verificação ao vivo (build + curl)**

Run (com API de fundo no ar):
```bash
cd web && npm run build && (npm run start -- -p 3939 > /tmp/m1.log 2>&1 &) \
  && for i in $(seq 1 40); do curl -s -o /dev/null localhost:3939/api/auth/logout -X POST && break; sleep 0.5; done \
  && curl -s -i -X POST localhost:3939/api/auth/login -H 'Content-Type: application/json' \
       -d '{"email":"athlete1@athletehub.example.com","password":"athlete1_pwd"}' | grep -Ei "HTTP/|set-cookie|role"
```
Expected: `HTTP/1.1 200`, header `set-cookie: aath_token=...; HttpOnly`, body com `"role":"ATHLETE"`. (Pare o server: `pkill -f "next start -p 3939"`.)

- [ ] **Step 4: Commit**

```bash
git add web/app/api/auth/
git commit -m "feat(web): BFF login/logout route handlers (httpOnly cookie)"
```

---

### Task 3: Proxy genérico para o FastAPI

**Files:**
- Create: `web/app/api/proxy/[...path]/route.ts`

**Interfaces:**
- Consumes: `resolveApiUrl`, `TOKEN_COOKIE`.
- Produces: `GET|POST|PUT|PATCH|DELETE /api/proxy/<path...>` → repassa ao FastAPI com `Authorization: Bearer`, preservando query, body (JSON/multipart) e respostas binárias.

- [ ] **Step 1: Implementar o proxy** — `web/app/api/proxy/[...path]/route.ts`:

```ts
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { resolveApiUrl } from "@/lib/config";
import { TOKEN_COOKIE } from "@/lib/session";

async function handle(request: NextRequest, params: Promise<{ path: string[] }>) {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Não autenticado" }, { status: 401 });

  const { path } = await params;
  const target = resolveApiUrl(path.join("/"), request.nextUrl.search);

  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  const contentType = request.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const init: RequestInit & { duplex?: "half" } = { method: request.method, headers };
  if (hasBody) {
    init.body = request.body;
    init.duplex = "half"; // streaming de body (JSON ou multipart) sem bufferizar
  }

  const upstream = await fetch(target, init);

  // Repassa a resposta preservando tipo e disposition (binários .zwo/.fit).
  const resHeaders = new Headers();
  for (const h of ["content-type", "content-disposition"]) {
    const v = upstream.headers.get(h);
    if (v) resHeaders.set(h, v);
  }
  return new NextResponse(upstream.body, { status: upstream.status, headers: resHeaders });
}

type Ctx = { params: Promise<{ path: string[] }> };

export const GET = (req: NextRequest, ctx: Ctx) => handle(req, ctx.params);
export const POST = (req: NextRequest, ctx: Ctx) => handle(req, ctx.params);
export const PUT = (req: NextRequest, ctx: Ctx) => handle(req, ctx.params);
export const PATCH = (req: NextRequest, ctx: Ctx) => handle(req, ctx.params);
export const DELETE = (req: NextRequest, ctx: Ctx) => handle(req, ctx.params);
```

- [ ] **Step 2: Verificação ao vivo (cookie jar + GET via proxy)**

Run (API de fundo no ar):
```bash
cd web && npm run build && (npm run start -- -p 3939 > /tmp/m1.log 2>&1 &) \
  && for i in $(seq 1 40); do curl -s -o /dev/null localhost:3939/login && break; sleep 0.5; done \
  && curl -s -c /tmp/jar -X POST localhost:3939/api/auth/login -H 'Content-Type: application/json' \
       -d '{"email":"athlete1@athletehub.example.com","password":"athlete1_pwd"}' > /dev/null \
  && echo "me:" && curl -s -b /tmp/jar localhost:3939/api/proxy/athletes/me | head -c 200 \
  && echo && echo "sem cookie (espera 401):" \
  && curl -s -o /dev/null -w "%{http_code}\n" localhost:3939/api/proxy/athletes/me
```
Expected: `me:` retorna JSON do atleta (com `full_name`); a chamada sem cookie retorna `401`. (Pare: `pkill -f "next start -p 3939"`.)

- [ ] **Step 3: Commit**

```bash
git add web/app/api/proxy/
git commit -m "feat(web): BFF proxy route forwarding to FastAPI with bearer token"
```

---

### Task 4: Middleware de proteção de rotas

**Files:**
- Create: `web/middleware.ts`

**Interfaces:**
- Produces: rotas não-públicas sem cookie `aath_token` → redirect 307 para `/login`.

- [ ] **Step 1: Implementar o middleware** — `web/middleware.ts`:

```ts
import { NextRequest, NextResponse } from "next/server";

// Repetido aqui de propósito: o middleware roda no edge runtime e não deve
// importar lib/session.ts (que usa Buffer/next/headers, Node-only).
const TOKEN_COOKIE = "aath_token";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const isPublic =
    pathname.startsWith("/login") ||
    pathname.startsWith("/api/auth") ||
    pathname === "/logo.svg";
  if (isPublic) return NextResponse.next();

  if (!req.cookies.has(TOKEN_COOKIE)) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

- [ ] **Step 2: Verificação ao vivo**

Run:
```bash
cd web && npm run build && (npm run start -- -p 3939 > /tmp/m1.log 2>&1 &) \
  && for i in $(seq 1 40); do curl -s -o /dev/null localhost:3939/login && break; sleep 0.5; done \
  && echo "sem cookie em / (espera 307 -> /login):" \
  && curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" localhost:3939/ \
  && echo "/login direto (espera 200):" \
  && curl -s -o /dev/null -w "%{http_code}\n" localhost:3939/login
```
Expected: `/` → `307` com `redirect_url` terminando em `/login`; `/login` → `200`. (Pare: `pkill -f "next start -p 3939"`.)

- [ ] **Step 3: Commit**

```bash
git add web/middleware.ts
git commit -m "feat(web): middleware gates authenticated routes on auth cookie"
```

---

### Task 5: Helper de dados no cliente + SWR provider

**Files:**
- Create: `web/lib/api.ts`
- Create: `web/components/SWRProvider.tsx`
- Modify: `web/app/layout.tsx` (envolver com `SWRProvider`)
- Test: `web/lib/__tests__/api.test.ts`

**Interfaces:**
- Consumes: SWR.
- Produces: `apiFetch(path: string, init?: RequestInit): Promise<Response>` (chama `/api/proxy/<path>`, trata 401 → logout+redirect); `jsonFetcher(path: string): Promise<any>`; `class ApiError extends Error { status: number }`; `<SWRProvider>`.

- [ ] **Step 1: Escrever o teste que falha** — `web/lib/__tests__/api.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../api";

describe("apiFetch", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("chama o proxy com o path limpo", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/athletes/me");
    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/athletes/me", undefined);
  });
});
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `cd web && npm test`
Expected: FAIL (módulo `../api` não existe).

- [ ] **Step 3: Implementar `lib/api.ts`**

```ts
"use client";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function handle(res: Response): Promise<Response> {
  if (res.status === 401) {
    // Sessão expirada/ausente — derruba e volta ao login.
    await fetch("/api/auth/logout", { method: "POST" });
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Sessão expirada");
  }
  return res;
}

/** Chama o proxy BFF. `path` é o caminho do FastAPI sem o /api/v1. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const clean = path.replace(/^\/+/, "");
  const res = await fetch(`/api/proxy/${clean}`, init);
  return handle(res);
}

/** Fetcher do SWR: GET + JSON. */
export async function jsonFetcher(path: string): Promise<unknown> {
  const res = await apiFetch(path);
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}
```

- [ ] **Step 4: Implementar o provider** — `web/components/SWRProvider.tsx`:

```tsx
"use client";

import { SWRConfig } from "swr";
import type { ReactNode } from "react";
import { jsonFetcher } from "@/lib/api";

export function SWRProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ fetcher: jsonFetcher, revalidateOnFocus: false }}>{children}</SWRConfig>
  );
}
```

- [ ] **Step 5: Envolver no root layout** — em `web/app/layout.tsx`, importar `SWRProvider` e aninhar dentro do `ThemeProvider`. Trocar:

```tsx
        <ThemeProvider>{children}</ThemeProvider>
```
por:
```tsx
        <ThemeProvider>
          <SWRProvider>{children}</SWRProvider>
        </ThemeProvider>
```
e adicionar no topo: `import { SWRProvider } from "@/components/SWRProvider";`

- [ ] **Step 6: Rodar os testes (verde)**

Run: `cd web && npm test`
Expected: PASS (8 testes).

- [ ] **Step 7: Commit**

```bash
git add web/lib/api.ts web/lib/__tests__/api.test.ts web/components/SWRProvider.tsx web/app/layout.tsx
git commit -m "feat(web): client apiFetch + SWR provider with 401 handling"
```

---

### Task 6: Ligar a página de login

**Files:**
- Modify: `web/app/(auth)/login/page.tsx` (vira client component com form controlado)

**Interfaces:**
- Consumes: `POST /api/auth/login`, `Button`, `Input`, `useRouter`.
- Produces: login funcional; redireciona ADMIN → `/admin`, atleta → `/`.

- [ ] **Step 1: Reescrever a página** — `web/app/(auth)/login/page.tsx`:

```tsx
"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("athlete1@athletehub.example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    setLoading(false);
    if (res.ok) {
      const { role } = await res.json();
      router.push(role === "ADMIN" ? "/admin" : "/");
      router.refresh();
    } else {
      setError("Falha no login. Verifique email e senha.");
    }
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
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verificar build/lint**

Run: `cd web && npm run build`
Expected: compila sem erros de tipo/lint.

- [ ] **Step 3: Commit**

```bash
git add "web/app/(auth)/login/page.tsx"
git commit -m "feat(web): wire login form to BFF, redirect by role"
```

---

### Task 7: Shell autenticado (server layout) + sidebar real + role-gating

**Files:**
- Modify: `web/app/(app)/layout.tsx` (vira Server Component)
- Create: `web/components/AppShell.tsx` (client: drawer + header — move a lógica do layout atual)
- Modify: `web/components/Sidebar.tsx` (rotas reais, props `role`/`userName`, seção Admin gateada, logout)

**Interfaces:**
- Consumes: `getSession`, `resolveApiUrl`, `Sidebar`, `useTheme`.
- Produces: `<AppShell role={Role|null} userName={string}>`; `Sidebar` aceita `{ role: Role | null; userName: string; onNavigate?: () => void }`.

- [ ] **Step 1: Reescrever a Sidebar** — `web/components/Sidebar.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  HeartPulse,
  Activity,
  ClipboardCheck,
  Upload,
  Flag,
  CalendarRange,
  Brain,
  ShieldCheck,
  LogOut,
  Moon,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { useTheme } from "./ThemeProvider";
import type { Role } from "@/lib/session";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Início", href: "/", icon: LayoutDashboard },
  { label: "Anamnese", href: "/anamnese", icon: HeartPulse },
  { label: "Forma & Carga", href: "/forma-carga", icon: Activity },
  { label: "Check-in", href: "/checkin", icon: ClipboardCheck },
  { label: "Importar", href: "/importar", icon: Upload },
  { label: "Provas", href: "/provas", icon: Flag },
  { label: "Plano", href: "/plano", icon: CalendarRange },
  { label: "Recomendações", href: "/recomendacoes", icon: Brain },
];

export const ADMIN_ITEMS: NavItem[] = [
  { label: "Painel do treinador", href: "/admin", icon: ShieldCheck },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "—";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function Sidebar({
  role,
  userName,
  onNavigate,
}: {
  role: Role | null;
  userName: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  const renderItem = (item: NavItem) => {
    const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
    const Icon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={onNavigate}
        className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
          active
            ? "text-white shadow-sm"
            : "text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700"
        }`}
        style={active ? { backgroundImage: "var(--gradient-button)" } : undefined}
      >
        <Icon className="h-5 w-5 shrink-0" />
        {item.label}
      </Link>
    );
  };

  return (
    <aside className="flex h-full w-64 flex-col bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800">
      <div className="flex items-center gap-3 px-6 h-16 border-b border-slate-100 dark:border-slate-800">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="" className="h-8 w-8" />
        <span className="font-bold text-slate-800 dark:text-slate-100">Meu App</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {NAV_ITEMS.map(renderItem)}

        {role === "ADMIN" && (
          <div className="pt-4 mt-4 border-t border-slate-100 dark:border-slate-800 space-y-1">
            <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Admin
            </p>
            {ADMIN_ITEMS.map(renderItem)}
          </div>
        )}
      </nav>

      <div className="border-t border-slate-100 dark:border-slate-800 p-3 space-y-1">
        <button
          type="button"
          onClick={toggleTheme}
          className="flex w-full items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
        >
          {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          {theme === "dark" ? "Tema claro" : "Tema escuro"}
        </button>

        <div className="flex items-center gap-3 px-3 py-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-200 dark:bg-slate-700 text-sm font-semibold text-slate-600 dark:text-slate-200">
            {initials(userName)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-700 dark:text-slate-200">
              {userName || "Usuário"}
            </p>
            <p className="truncate text-xs text-slate-400">{role === "ADMIN" ? "Treinador" : "Atleta"}</p>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Sair"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <LogOut className="h-5 w-5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Criar o `AppShell`** — `web/components/AppShell.tsx`:

```tsx
"use client";

import { useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import type { Role } from "@/lib/session";

export function AppShell({
  role,
  userName,
  children,
}: {
  role: Role | null;
  userName: string;
  children: ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 dark:bg-slate-950">
      <div className="hidden md:block">
        <Sidebar role={role} userName={userName} />
      </div>

      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 md:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Abrir menu"
          className="rounded-lg p-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <Menu className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="" className="h-7 w-7" />
          <span className="font-bold text-slate-800 dark:text-slate-100">Meu App</span>
        </div>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-slate-900/50"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 animate-slide-in-left">
            <div className="relative h-full">
              <Sidebar role={role} userName={userName} onNavigate={() => setMobileOpen(false)} />
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Fechar menu"
                className="absolute right-3 top-4 rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      )}

      <main className="flex-1 overflow-y-auto pt-14 md:pt-0">
        <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: Converter o `(app)/layout.tsx` em Server Component** — substituir TODO o conteúdo de `web/app/(app)/layout.tsx` por:

```tsx
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { resolveApiUrl } from "@/lib/config";
import { AppShell } from "@/components/AppShell";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();
  if (!session) redirect("/login");

  let userName = "";
  try {
    const res = await fetch(resolveApiUrl("athletes/me"), {
      headers: { Authorization: `Bearer ${session.token}` },
      cache: "no-store",
    });
    if (res.ok) userName = (await res.json()).full_name ?? "";
  } catch {
    // backend indisponível — segue com nome vazio; middleware já garantiu o cookie
  }

  return (
    <AppShell role={session.role} userName={userName}>
      {children}
    </AppShell>
  );
}
```

- [ ] **Step 4: Verificar build/lint**

Run: `cd web && npm run build`
Expected: compila sem erros. (Pode falhar em "page conflict" / rotas inexistentes só na Task 8 — aqui o objetivo é compilar os componentes; se o build acusar conflito de `/`, ele será resolvido na Task 8. Se compilar, ótimo.)

- [ ] **Step 5: Commit**

```bash
git add web/components/Sidebar.tsx web/components/AppShell.tsx "web/app/(app)/layout.tsx"
git commit -m "feat(web): server-rendered app shell with role-gated sidebar + logout"
```

---

### Task 8: Overview + stubs navegáveis + correção de rota raiz

**Files:**
- Delete: `web/app/page.tsx` (conflita com `(app)/page.tsx` em `/`)
- Delete: `web/app/(app)/dashboard/page.tsx` (substituída pelo overview em `/`)
- Create: `web/components/ComingSoon.tsx`
- Create: `web/app/(app)/page.tsx` (overview esqueleto)
- Create: `web/app/(app)/anamnese/page.tsx`, `forma-carga/page.tsx`, `checkin/page.tsx`, `importar/page.tsx`, `provas/page.tsx`, `plano/page.tsx`, `recomendacoes/page.tsx` (stubs)
- Create: `web/app/(app)/admin/page.tsx` (stub gateado por papel)

**Interfaces:**
- Consumes: `Card`, `Button`, `getSession`.
- Produces: rotas `(app)/*` navegáveis; `/` = overview; `/admin` redireciona não-ADMIN para `/`.

- [ ] **Step 1: Remover a rota raiz antiga e o dashboard de exemplo**

```bash
git rm web/app/page.tsx "web/app/(app)/dashboard/page.tsx"
```

- [ ] **Step 2: Criar o `ComingSoon`** — `web/components/ComingSoon.tsx`:

```tsx
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
```

- [ ] **Step 3: Criar o overview** — `web/app/(app)/page.tsx`:

```tsx
import Link from "next/link";
import { HeartPulse, Activity, Flag, Brain } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

const cards = [
  { label: "Anamnese", hint: "status do seu perfil", icon: HeartPulse },
  { label: "Forma (TSB)", hint: "CTL · ATL · TSB", icon: Activity },
  { label: "Próxima prova", hint: "contagem regressiva", icon: Flag },
  { label: "Fase de hoje", hint: "bloco do plano", icon: Brain },
];

export default function OverviewPage() {
  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-slate-800 dark:text-slate-100">
            Visão geral
          </h1>
          <p className="text-sm text-slate-500">Seu painel de treino.</p>
        </div>
        <Link href="/recomendacoes">
          <Button>
            <Brain className="h-4 w-4" />
            Gerar recomendação
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.label}
              className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-5"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400">
                <Icon className="h-5 w-5" />
              </span>
              <p className="mt-4 text-2xl font-bold text-slate-300 dark:text-slate-600">—</p>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">{c.label}</p>
              <p className="text-xs text-slate-400">{c.hint}</p>
            </div>
          );
        })}
      </div>

      <Card title="Dados ao vivo">
        <p className="text-sm text-slate-500">
          Os indicadores acima passam a refletir seus dados reais no marco <strong>M2</strong>.
        </p>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Criar os stubs do atleta** — cada arquivo abaixo, usando `ComingSoon` com o título e marco indicados:

`web/app/(app)/anamnese/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";
export default function Page() {
  return <ComingSoon title="🩺 Anamnese" milestone="M2" />;
}
```
`web/app/(app)/forma-carga/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";
export default function Page() {
  return <ComingSoon title="📈 Forma & Carga" milestone="M2" />;
}
```
`web/app/(app)/checkin/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";
export default function Page() {
  return <ComingSoon title="📝 Check-in diário" milestone="M2" />;
}
```
`web/app/(app)/importar/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";
export default function Page() {
  return <ComingSoon title="📥 Importar" milestone="M2" />;
}
```
`web/app/(app)/provas/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";
export default function Page() {
  return <ComingSoon title="🏁 Provas" milestone="M3" />;
}
```
`web/app/(app)/plano/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";
export default function Page() {
  return <ComingSoon title="📅 Plano" milestone="M3" />;
}
```
`web/app/(app)/recomendacoes/page.tsx`:
```tsx
import { ComingSoon } from "@/components/ComingSoon";
export default function Page() {
  return <ComingSoon title="🧠 Recomendações" milestone="M4" />;
}
```

- [ ] **Step 5: Criar o stub do admin (gateado)** — `web/app/(app)/admin/page.tsx`:

```tsx
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { ComingSoon } from "@/components/ComingSoon";

export default async function AdminPage() {
  const session = await getSession();
  if (session?.role !== "ADMIN") redirect("/");
  return <ComingSoon title="📋 Painel do treinador" milestone="M5" />;
}
```

- [ ] **Step 6: Verificar build/lint**

Run: `cd web && npm run build`
Expected: compila; rotas geradas incluem `/`, `/login`, `/anamnese`, `/forma-carga`, `/checkin`, `/importar`, `/provas`, `/plano`, `/recomendacoes`, `/admin`. Sem conflito de rota `/`.

- [ ] **Step 7: Verificação ao vivo (gate de aceitação do M1)**

Run (API de fundo no ar):
```bash
cd web && (npm run start -- -p 3939 > /tmp/m1.log 2>&1 &) \
  && for i in $(seq 1 40); do curl -s -o /dev/null localhost:3939/login && break; sleep 0.5; done
# 1) login atleta -> cookie
curl -s -c /tmp/jar -X POST localhost:3939/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"athlete1@athletehub.example.com","password":"athlete1_pwd"}' -o /dev/null
# 2) overview acessível com cookie (espera 200)
curl -s -b /tmp/jar -o /dev/null -w "/ = %{http_code}\n" localhost:3939/
# 3) stub navegável (espera 200)
curl -s -b /tmp/jar -o /dev/null -w "/anamnese = %{http_code}\n" localhost:3939/anamnese
# 4) atleta em /admin -> redirect para / (espera 307)
curl -s -b /tmp/jar -o /dev/null -w "/admin (atleta) = %{http_code} %{redirect_url}\n" localhost:3939/admin
# 5) admin loga e acessa /admin (espera 200)
curl -s -c /tmp/jar_admin -X POST localhost:3939/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@athletehub.example.com","password":"admin_dev_pwd"}' -o /dev/null
curl -s -b /tmp/jar_admin -o /dev/null -w "/admin (admin) = %{http_code}\n" localhost:3939/admin
```
Expected: `/ = 200`; `/anamnese = 200`; `/admin (atleta) = 307` redirecionando para `/`; `/admin (admin) = 200`. (Pare: `pkill -f "next start -p 3939"`.)

Verificação manual (navegador, opcional): `npm run dev`, logar como `athlete1` → cai no overview, navega pelas abas (stubs), alterna tema, faz logout → volta ao login.

- [ ] **Step 8: Commit**

```bash
git add web/app web/components/ComingSoon.tsx
git commit -m "feat(web): overview + navigable route stubs + role-gated admin"
```

---

## Self-Review (autor do plano)

- **Cobertura do spec (parte M1):** BFF login/logout (Task 2) + proxy (Task 3) + cookie httpOnly (Tasks 2-3); `middleware.ts` protegendo `(app)` (Task 4); `lib/session` decodifica papel (Task 1); `lib/api`+SWR (Task 5); login real com redirect por papel (Task 6); shell server-rendered + nav real + role-gating + logout (Task 7); overview novo + rotas navegáveis + `/admin` gateado (Task 8). As telas com dados reais (anamnese, forma & carga, etc.) são M2-M5 — aqui ficam como stubs `ComingSoon`, por design da migração faseada.
- **Placeholders:** nenhum "TBD/TODO"; todo código presente. Os stubs `ComingSoon` são entregáveis intencionais do M1 (shell navegável sem 404), não placeholders de plano.
- **Consistência de tipos/nomes:** `TOKEN_COOKIE`/`Role`/`decodeJwtRole`/`getSession` (Task 1) reusados em Tasks 2,3,7,8; `resolveApiUrl` (Task 1) em Tasks 2,3,7; `apiFetch`/`jsonFetcher` (Task 5) prontos para M2; `Sidebar({role,userName,onNavigate})` (Task 7) casa com `AppShell` (Task 7); rota `/` (overview, Task 8) casa com o redirect do login (Task 6) e o item "Início" da nav (Task 7).
- **Rota raiz:** resolvido o conflito `app/page.tsx` vs `app/(app)/page.tsx` removendo o primeiro (Task 8, Step 1).

## Próximos marcos (planos próprios após o M1)

- **M2** Atleta core: `/anamnese`, `/checkin`, `/forma-carga` (recharts), `/importar` + overview com dados reais.
- **M3** Planejamento: `/provas`, `/plano`.
- **M4** Loop de IA: `/recomendacoes` (gerar/exportar/feedback) + treinos de teste.
- **M5** Admin: `/admin` (KPIs + atletas + feedbacks).
- **M6** Paridade + aposentar Streamlit (compose/runbook).
