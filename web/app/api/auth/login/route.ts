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
