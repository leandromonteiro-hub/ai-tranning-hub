import { NextResponse } from "next/server";
import { resolveApiUrl } from "@/lib/config";
import { decodeJwtRole, TOKEN_COOKIE } from "@/lib/session";

export async function POST(request: Request) {
  let credential: string | undefined;
  let invite_code: string | undefined;
  try {
    ({ credential, invite_code } = await request.json());
  } catch {
    return NextResponse.json({ error: "Corpo inválido" }, { status: 400 });
  }
  const res = await fetch(resolveApiUrl("auth/google"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credential, invite_code: invite_code ?? null }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    return NextResponse.json({ error: body.detail ?? "Falha no login" }, { status: res.status });
  }
  const { access_token } = await res.json();
  const response = NextResponse.json({ ok: true, role: decodeJwtRole(access_token) ?? null });
  response.cookies.set(TOKEN_COOKIE, access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 30,
  });
  return response;
}
