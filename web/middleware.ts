import { NextRequest, NextResponse } from "next/server";

// Repetido aqui de propósito: o middleware roda no edge runtime e não deve
// importar lib/session.ts (que usa Buffer/next/headers, Node-only).
const TOKEN_COOKIE = "aath_token";

// Auto-login DEV (temporário): quando DEV_AUTO_LOGIN=1, em vez de mandar para
// /login, o middleware autentica sozinho com um atleta fixo e grava o cookie.
// Desligado por padrão — produção continua exigindo login normal.
const DEV_AUTO_LOGIN = process.env.DEV_AUTO_LOGIN === "1";
const DEV_EMAIL = process.env.DEV_LOGIN_EMAIL ?? "";
const DEV_PASSWORD = process.env.DEV_LOGIN_PASSWORD ?? "";
const API_BASE_URL = (process.env.API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");

async function devLogin(): Promise<string | null> {
  if (!DEV_AUTO_LOGIN || !DEV_EMAIL || !DEV_PASSWORD) return null;
  try {
    const body = new URLSearchParams({ username: DEV_EMAIL, password: DEV_PASSWORD });
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) return null;
    const { access_token } = await res.json();
    return typeof access_token === "string" ? access_token : null;
  } catch {
    return null;
  }
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const isPublic =
    pathname === "/login" ||
    pathname.startsWith("/login/") ||
    pathname === "/api/auth" ||
    pathname.startsWith("/api/auth/") ||
    pathname === "/logo.svg";
  if (isPublic) return NextResponse.next();

  if (!req.cookies.has(TOKEN_COOKIE)) {
    // Modo DEV sem login: tenta autenticar sozinho e segue com o cookie gravado.
    const token = await devLogin();
    if (token) {
      const res = NextResponse.redirect(req.nextUrl);
      res.cookies.set(TOKEN_COOKIE, token, {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: 60 * 30,
      });
      return res;
    }
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
