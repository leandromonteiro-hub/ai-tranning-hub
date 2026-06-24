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
