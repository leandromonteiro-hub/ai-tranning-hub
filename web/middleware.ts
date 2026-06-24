import { NextRequest, NextResponse } from "next/server";

// Repetido aqui de propósito: o middleware roda no edge runtime e não deve
// importar lib/session.ts (que usa Buffer/next/headers, Node-only).
const TOKEN_COOKIE = "aath_token";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const isPublic =
    pathname === "/login" ||
    pathname.startsWith("/login/") ||
    pathname === "/api/auth" ||
    pathname.startsWith("/api/auth/") ||
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
