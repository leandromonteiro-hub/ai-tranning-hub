import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { publicOrigin, resolveApiUrl } from "@/lib/config";
import { TOKEN_COOKIE } from "@/lib/session";

/**
 * Retorno do OAuth da Whoop. Chega pelo NAVEGADOR do atleta, então tem o cookie
 * de sessão — é assim que o backend sabe qual atleta está conectando (e o `state`
 * assinado confirma). Repassa code+state e devolve o atleta para /conexoes com o
 * resultado na query string.
 */
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const back = new URL("/conexoes", publicOrigin(request.headers));

  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) {
    back.searchParams.set("whoop", "erro");
    back.searchParams.set("motivo", "sessao_expirada");
    return NextResponse.redirect(back);
  }

  if (!code || !state) {
    back.searchParams.set("whoop", "erro");
    // A Whoop devolve error/error_description quando o atleta nega a autorização.
    back.searchParams.set(
      "motivo",
      request.nextUrl.searchParams.get("error") ?? "callback_incompleto",
    );
    return NextResponse.redirect(back);
  }

  const upstream = await fetch(resolveApiUrl("whoop/callback", ""), {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ code, state }),
  });

  if (upstream.ok) {
    back.searchParams.set("whoop", "ok");
  } else {
    const body = await upstream.json().catch(() => ({}));
    back.searchParams.set("whoop", "erro");
    if (body?.detail) back.searchParams.set("motivo", String(body.detail));
  }
  return NextResponse.redirect(back);
}
